#!/usr/bin/env python3
"""
XAU/USD 200-Day Backtest
Strategy: EMA 21/50 crossover + EMA 200 trend filter + RSI filter + ATR stops
Mirrors the TradingView Pine Script strategy exactly.
"""

import sys
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

# ─── PARAMETERS (match Pine Script defaults) ──────────────────────────────────

END_DATE   = datetime(2026, 5, 31)
START_DATE = END_DATE - timedelta(days=200)

EMA_FAST   = 21
EMA_SLOW   = 50
EMA_TREND  = 200

RSI_LEN    = 14
RSI_OB     = 70      # overbought — no longs above this
RSI_OS     = 30      # oversold   — no shorts below this

ATR_LEN    = 14
SL_MULT    = 1.5     # stop loss  × ATR
TP_MULT    = 3.0     # take profit × ATR  (2:1 R:R)

INITIAL_CAP   = 10_000.0
POSITION_PCT  = 0.10     # 10% of equity per trade
COMMISSION    = 0.0007   # 0.07% per side

ALLOW_LONG  = True
ALLOW_SHORT = True

# ─── DATA ─────────────────────────────────────────────────────────────────────

def fetch_data() -> pd.DataFrame:
    # Fetch extra history so EMAs are warm before backtest window
    fetch_start = START_DATE - timedelta(days=400)
    ticker = yf.Ticker("GC=F")   # Gold Futures — same as XAUUSD
    df = ticker.history(start=fetch_start.strftime("%Y-%m-%d"),
                        end=(END_DATE + timedelta(days=1)).strftime("%Y-%m-%d"))
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)
    return df

# ─── INDICATORS ───────────────────────────────────────────────────────────────

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["ema_fast"]  = df["Close"].ewm(span=EMA_FAST,  adjust=False).mean()
    df["ema_slow"]  = df["Close"].ewm(span=EMA_SLOW,  adjust=False).mean()
    df["ema_trend"] = df["Close"].ewm(span=EMA_TREND, adjust=False).mean()

    # RSI
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0).ewm(com=RSI_LEN - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=RSI_LEN - 1, adjust=False).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))

    # ATR
    hl  = df["High"] - df["Low"]
    hcp = (df["High"] - df["Close"].shift()).abs()
    lcp = (df["Low"]  - df["Close"].shift()).abs()
    tr  = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)
    df["atr"] = tr.ewm(com=ATR_LEN - 1, adjust=False).mean()

    # Crossover signals
    df["cross_up"]   = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift() <= df["ema_slow"].shift())
    df["cross_down"] = (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast"].shift() >= df["ema_slow"].shift())

    return df

# ─── BACKTEST ENGINE ──────────────────────────────────────────────────────────

def run_backtest(df: pd.DataFrame) -> tuple[list[dict], pd.Series]:
    window = df[(df.index >= START_DATE) & (df.index <= END_DATE)].copy()

    trades    = []
    equity    = INITIAL_CAP
    position  = None   # dict when in a trade
    equity_curve = {window.index[0]: equity}

    for ts, row in window.iterrows():
        # ── Check if existing position hit SL or TP ──
        if position is not None:
            hit_tp = hit_sl = False
            if position["side"] == "long":
                if row["Low"]  <= position["sl"]: hit_sl = True
                if row["High"] >= position["tp"]: hit_tp = True
            else:
                if row["High"] >= position["sl"]: hit_sl = True
                if row["Low"]  <= position["tp"]: hit_tp = True

            if hit_tp or hit_sl:
                exit_price = position["tp"] if hit_tp else position["sl"]
                pnl_pts    = (exit_price - position["entry"]) if position["side"] == "long" \
                             else (position["entry"] - exit_price)
                pnl_pct    = pnl_pts / position["entry"]
                gross_pnl  = position["size"] * pnl_pct
                net_pnl    = gross_pnl - 2 * COMMISSION * position["size"]
                equity    += net_pnl
                trades.append({
                    "entry_date":  position["entry_date"],
                    "exit_date":   ts,
                    "side":        position["side"],
                    "entry":       round(position["entry"], 2),
                    "exit":        round(exit_price, 2),
                    "sl":          round(position["sl"], 2),
                    "tp":          round(position["tp"], 2),
                    "result":      "TP" if hit_tp else "SL",
                    "pnl_pts":     round(pnl_pts, 2),
                    "net_pnl":     round(net_pnl, 2),
                    "equity":      round(equity, 2),
                })
                position = None

        # ── Check for new entry signals ──
        if position is None:
            above_trend = row["Close"] > row["ema_trend"]
            long_sig  = row["cross_up"]   and above_trend   and row["rsi"] < RSI_OB and ALLOW_LONG
            short_sig = row["cross_down"] and not above_trend and row["rsi"] > RSI_OS and ALLOW_SHORT

            if long_sig or short_sig:
                side   = "long" if long_sig else "short"
                entry  = row["Close"]
                atr    = row["atr"]
                sl     = entry - atr * SL_MULT if side == "long" else entry + atr * SL_MULT
                tp     = entry + atr * TP_MULT if side == "long" else entry - atr * TP_MULT
                size   = equity * POSITION_PCT
                position = dict(side=side, entry=entry, sl=sl, tp=tp,
                                size=size, entry_date=ts)

        equity_curve[ts] = round(equity, 2)

    # Close open position at end of range
    if position is not None:
        last = window.iloc[-1]
        exit_price = last["Close"]
        pnl_pts    = (exit_price - position["entry"]) if position["side"] == "long" \
                     else (position["entry"] - exit_price)
        pnl_pct    = pnl_pts / position["entry"]
        gross_pnl  = position["size"] * pnl_pct
        net_pnl    = gross_pnl - 2 * COMMISSION * position["size"]
        equity    += net_pnl
        trades.append({
            "entry_date":  position["entry_date"],
            "exit_date":   window.index[-1],
            "side":        position["side"],
            "entry":       round(position["entry"], 2),
            "exit":        round(exit_price, 2),
            "sl":          round(position["sl"], 2),
            "tp":          round(position["tp"], 2),
            "result":      "OPEN→close",
            "pnl_pts":     round(pnl_pts, 2),
            "net_pnl":     round(net_pnl, 2),
            "equity":      round(equity, 2),
        })

    return trades, pd.Series(equity_curve)

# ─── REPORT ───────────────────────────────────────────────────────────────────

def report(trades: list[dict], equity_curve: pd.Series) -> None:
    if not trades:
        print("No trades triggered in the backtest window.")
        return

    df_t       = pd.DataFrame(trades)
    wins       = df_t[df_t["net_pnl"] > 0]
    losses     = df_t[df_t["net_pnl"] <= 0]
    total      = len(df_t)
    win_rate   = len(wins) / total * 100
    net_profit = df_t["net_pnl"].sum()
    gross_win  = wins["net_pnl"].sum()
    gross_loss = losses["net_pnl"].sum()
    pf         = gross_win / abs(gross_loss) if gross_loss != 0 else float("inf")
    final_eq   = INITIAL_CAP + net_profit
    ret_pct    = net_profit / INITIAL_CAP * 100

    # Max drawdown
    peak = equity_curve.cummax()
    dd   = (equity_curve - peak) / peak * 100
    max_dd = dd.min()

    sep = "─" * 52
    print(f"\n{'XAU/USD 200-Day Backtest Results':^52}")
    print(sep)
    print(f"  Period          {START_DATE.strftime('%Y-%m-%d')}  →  {END_DATE.strftime('%Y-%m-%d')}")
    print(f"  Strategy        EMA {EMA_FAST}/{EMA_SLOW} cross | EMA {EMA_TREND} trend | RSI | ATR stops")
    print(f"  SL / TP         {SL_MULT}× ATR  /  {TP_MULT}× ATR  (R:R = 1:{TP_MULT/SL_MULT:.1f})")
    print(sep)
    print(f"  Initial capital   ${INITIAL_CAP:>10,.2f}")
    print(f"  Final equity      ${final_eq:>10,.2f}")
    net_color = "+" if net_profit >= 0 else ""
    print(f"  Net profit        {net_color}${net_profit:>9,.2f}  ({net_color}{ret_pct:.2f}%)")
    print(f"  Max drawdown      {max_dd:.2f}%")
    print(f"  Profit factor     {pf:.2f}")
    print(sep)
    print(f"  Total trades      {total}")
    print(f"  Winners           {len(wins)}  ({win_rate:.1f}%)")
    print(f"  Losers            {len(losses)}  ({100 - win_rate:.1f}%)")
    print(f"  Avg win           ${wins['net_pnl'].mean():,.2f}" if len(wins) else "  Avg win           —")
    print(f"  Avg loss          ${losses['net_pnl'].mean():,.2f}" if len(losses) else "  Avg loss          —")
    print(f"  Best trade        ${df_t['net_pnl'].max():,.2f}")
    print(f"  Worst trade       ${df_t['net_pnl'].min():,.2f}")
    print(sep)
    print(f"\n{'Trade Log':^52}")
    print(f"  {'#':<3} {'Date In':<12} {'Date Out':<12} {'Side':<6} {'Entry':>8} {'Exit':>8} {'Result':<12} {'P&L':>9}")
    print(f"  {'─'*3} {'─'*11} {'─'*11} {'─'*5} {'─'*8} {'─'*8} {'─'*11} {'─'*9}")
    for i, t in enumerate(trades, 1):
        din  = t["entry_date"].strftime("%Y-%m-%d")
        dout = t["exit_date"].strftime("%Y-%m-%d")
        pnl  = f"+${t['net_pnl']:,.0f}" if t["net_pnl"] >= 0 else f"-${abs(t['net_pnl']):,.0f}"
        print(f"  {i:<3} {din:<12} {dout:<12} {t['side']:<6} {t['entry']:>8.2f} {t['exit']:>8.2f} {t['result']:<12} {pnl:>9}")
    print()


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching XAU/USD data...")
    df = fetch_data()
    df = add_indicators(df)
    print(f"Data loaded: {len(df)} bars  ({df.index[0].date()} → {df.index[-1].date()})")
    trades, equity_curve = run_backtest(df)
    report(trades, equity_curve)
