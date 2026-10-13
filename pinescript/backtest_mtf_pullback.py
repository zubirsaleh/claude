"""Python port of mtf_pullback_buy_strategy.pine for offline backtesting.

Usage: python pinescript/backtest_mtf_pullback.py <h1.csv> [days]
CSV columns: time (UTC), open, high, low, close — 1-hour bars with enough
history before the test window to warm up EMA 200 and the daily EMAs.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Params:
    d_fast: int = 8
    d_slow: int = 21
    h_fast: int = 50
    h_slow: int = 200
    rsi_len: int = 6
    rsi_level: float = 20.0
    rsi_lookback: int = 3
    swing_len: int = 50
    pivot_len: int = 3
    min_retrace: float = 50.0
    max_retrace: float = 100.0
    wick_ratio: float = 2.0
    opp_wick_ratio: float = 1.0
    touch_tol_pct: float = 0.10
    touch_lookback: int = 2
    min_rr: float = 1.5
    atr_len: int = 14
    sl_atr_mult: float = 0.2
    mintick: float = 0.01
    commission_pct: float = 0.05
    equity_pct: float = 10.0
    initial_capital: float = 10_000.0


def rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def compute_signals(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    o, h, l, c = df.open, df.high, df.low, df.close

    # 1. Daily trend from the previous completed session (CME session rolls at ~22:00 UTC).
    session = (df.time + pd.Timedelta(hours=2)).dt.date
    daily_close = c.groupby(session).last()
    d_fast = ema(daily_close, p.d_fast).shift(1)
    d_slow = ema(daily_close, p.d_slow).shift(1)
    df["d_fast"] = session.map(d_fast)
    df["d_slow"] = session.map(d_slow)
    df["c1"] = df.d_fast > df.d_slow

    # 2. H1 trend
    df["h_fast"] = ema(c, p.h_fast)
    df["h_slow"] = ema(c, p.h_slow)
    df["c2"] = df.h_fast > df.h_slow

    # 3. RSI
    delta = c.diff()
    up = rma(delta.clip(lower=0), p.rsi_len)
    dn = rma(-delta.clip(upper=0), p.rsi_len)
    df["rsi"] = np.where(dn == 0, 100.0, 100 - 100 / (1 + up / dn.replace(0, np.nan)))
    df["rsi_min"] = df.rsi.rolling(p.rsi_lookback + 1).min()
    df["c3"] = df.rsi_min <= p.rsi_level

    # 4. Retracement of the previous move
    n = len(df)
    hv, lv = h.to_numpy(), l.to_numpy()
    leg_high = np.full(n, np.nan)
    leg_low = np.full(n, np.nan)
    pull_low = np.full(n, np.nan)
    hi_off = np.zeros(n, dtype=int)
    for i in range(p.swing_len - 1, n):
        win = hv[i - p.swing_len + 1:i + 1]
        off = p.swing_len - 1 - int(np.argmax(win))
        j = i - off
        hi_off[i] = off
        leg_high[i] = hv[j]
        if j - p.swing_len + 1 >= 0:
            leg_low[i] = lv[j - p.swing_len + 1:j + 1].min()
        pull_low[i] = lv[j:i + 1].min()
    rng = leg_high - leg_low
    with np.errstate(invalid="ignore", divide="ignore"):
        retrace = np.where((hi_off > 0) & (rng > 0), (leg_high - pull_low) / rng * 100, np.nan)
    df["leg_high"], df["pull_low"], df["retrace"] = leg_high, pull_low, retrace
    df["c4"] = (df.retrace >= p.min_retrace) & (df.retrace <= p.max_retrace)

    # 5. Confirmation candle
    body = (c - o).abs()
    body_adj = body.clip(lower=p.mintick)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    engulf = (c > o) & (c.shift(1) < o.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1)) & (body > (c.shift(1) - o.shift(1)).abs())
    hammer = (lower >= p.wick_ratio * body_adj) & (upper <= p.opp_wick_ratio * body_adj)
    inv_hammer = (upper >= p.wick_ratio * body_adj) & (lower <= p.opp_wick_ratio * body_adj)
    df["candle"] = np.select([engulf, hammer, inv_hammer], ["Engulfing", "Hammer", "Inv. Hammer"], "")
    df["c5"] = df.candle != ""

    # 6. Touch EMA 50 / EMA 200 / ascending trendline through last two confirmed pivot lows
    k = p.pivot_len
    tl = np.full(n, np.nan)
    last_pl = prev_pl = np.nan
    last_bar = prev_bar = -1
    for i in range(2 * k, n):
        piv = i - k
        if lv[piv] < lv[piv - k:piv].min() and lv[piv] <= lv[piv + 1:i + 1].min():
            prev_pl, prev_bar = last_pl, last_bar
            last_pl, last_bar = lv[piv], piv
        if not np.isnan(prev_pl) and last_pl > prev_pl:
            tl[i] = last_pl + (last_pl - prev_pl) / (last_bar - prev_bar) * (i - last_bar)
    tol = p.touch_tol_pct / 100

    def touches(level):
        return (l <= level * (1 + tol)) & (h >= level * (1 - tol))

    touch_now = touches(df.h_fast) | touches(df.h_slow) | touches(pd.Series(tl)).fillna(False)
    df["c6"] = touch_now.astype(int).rolling(p.touch_lookback + 1, min_periods=1).max() > 0

    # 7. Risk-reward
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = rma(tr, p.atr_len)
    df["stop"] = np.minimum(l, df.pull_low) - atr * p.sl_atr_mult
    df["target"] = df.leg_high
    risk = c - df.stop
    df["rr"] = np.where(risk > 0, (df.target - c) / risk, np.nan)
    df["c7"] = df.rr >= p.min_rr

    conds = [f"c{i}" for i in range(1, 8)]
    df[conds] = df[conds].fillna(False).astype(bool)
    df["signal"] = df[conds].all(axis=1)
    df["met"] = df[conds].sum(axis=1)
    return df


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry: float
    stop: float
    target: float
    candle: str
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    result: str = "open"
    pnl: float = 0.0
    r_multiple: float = 0.0
    qty: float = 0.0
    extra: dict = field(default_factory=dict)


def run_backtest(df: pd.DataFrame, p: Params, start: pd.Timestamp) -> tuple[list[Trade], float]:
    equity = p.initial_capital
    trades: list[Trade] = []
    pos: Trade | None = None
    comm = p.commission_pct / 100
    for i in range(len(df)):
        r = df.iloc[i]
        if pos is not None:
            hit_stop, hit_tp = r.low <= pos.stop, r.high >= pos.target
            if hit_stop or hit_tp:
                if hit_stop and hit_tp:
                    # TradingView's emulator: price travels to the extreme nearest the open first.
                    stop_first = (r.open - r.low) < (r.high - r.open)
                    hit_tp = not stop_first
                if hit_tp:
                    px, res = max(r.open, pos.target), "TP"
                else:
                    px, res = min(r.open, pos.stop), "SL"
                pos.exit_time, pos.exit, pos.result = r.time, px, res
                pos.pnl = (px - pos.entry) * pos.qty - comm * (px + pos.entry) * pos.qty
                pos.r_multiple = (px - pos.entry) / (pos.entry - pos.stop)
                equity += pos.pnl
                trades.append(pos)
                pos = None
        if pos is None and r.signal and r.time >= start:
            qty = equity * p.equity_pct / 100 / r.close
            pos = Trade(r.time, r.close, r.stop, r.target, r.candle, qty=qty)
    if pos is not None:
        last = df.iloc[-1]
        pos.exit_time, pos.exit = last.time, last.close
        pos.pnl = (last.close - pos.entry) * pos.qty - comm * (last.close + pos.entry) * pos.qty
        pos.r_multiple = (last.close - pos.entry) / (pos.entry - pos.stop)
        trades.append(pos)
    return trades, equity


def summarize(trades: list[Trade], p: Params, final_equity: float) -> dict:
    closed = [t for t in trades if t.result != "open"]
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    eq = np.cumsum([p.initial_capital] + [t.pnl for t in closed])
    dd = (eq - np.maximum.accumulate(eq)).min() if len(eq) > 1 else 0.0
    return {
        "trades": len(closed),
        "open": len(trades) - len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(closed) * 100 if closed else float("nan"),
        "net_pnl": final_equity - p.initial_capital,
        "net_pct": (final_equity / p.initial_capital - 1) * 100,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else float("nan"),
        "avg_r": float(np.mean([t.r_multiple for t in closed])) if closed else float("nan"),
        "max_dd": float(dd),
    }


def main() -> None:
    path = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    raw = pd.read_csv(path, parse_dates=["time"])
    p = Params()
    df = compute_signals(raw, p)
    start = df.time.iloc[-1] - pd.Timedelta(days=days)
    trades, final_eq = run_backtest(df, p, start)
    print(summarize(trades, p, final_eq))
    for t in trades:
        print(t.entry_time, t.candle, round(t.entry, 2), round(t.stop, 2), round(t.target, 2), t.result, round(t.r_multiple, 2))


if __name__ == "__main__":
    main()
