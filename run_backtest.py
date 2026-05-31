#!/usr/bin/env python3
"""Run XAU/USD backtest using real FMP GCUSD data."""

import json
import pandas as pd
from datetime import datetime

# ── PARAMETERS ────────────────────────────────────────────────────────────────
EMA_FAST  = 21
EMA_SLOW  = 50
EMA_TREND = 200
RSI_LEN   = 14
RSI_OB    = 70
RSI_OS    = 30
ATR_LEN   = 14
SL_MULT   = 1.5
TP_MULT   = 3.0
INITIAL_CAP  = 10_000.0
POSITION_PCT = 0.10
COMMISSION   = 0.0007

# ── LOAD DATA ─────────────────────────────────────────────────────────────────
with open("gcusd_data.json") as f:
    raw = json.load(f)

df = pd.DataFrame(raw)[["date","open","high","low","close","volume"]]
df.columns = ["Date","Open","High","Low","Close","Volume"]
df["Date"] = pd.to_datetime(df["Date"])
df = df.sort_values("Date").reset_index(drop=True)

# ── INDICATORS ────────────────────────────────────────────────────────────────
df["ema_fast"]  = df["Close"].ewm(span=EMA_FAST,  adjust=False).mean()
df["ema_slow"]  = df["Close"].ewm(span=EMA_SLOW,  adjust=False).mean()
df["ema_trend"] = df["Close"].ewm(span=EMA_TREND, adjust=False).mean()

delta = df["Close"].diff()
gain  = delta.clip(lower=0).ewm(com=RSI_LEN-1, adjust=False).mean()
loss  = (-delta.clip(upper=0)).ewm(com=RSI_LEN-1, adjust=False).mean()
df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))

hl  = df["High"] - df["Low"]
hcp = (df["High"] - df["Close"].shift()).abs()
lcp = (df["Low"]  - df["Close"].shift()).abs()
df["atr"] = pd.concat([hl, hcp, lcp], axis=1).max(axis=1).ewm(com=ATR_LEN-1, adjust=False).mean()

df["cross_up"]   = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift() <= df["ema_slow"].shift())
df["cross_down"] = (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast"].shift() >= df["ema_slow"].shift())

# ── BACKTEST ──────────────────────────────────────────────────────────────────
trades   = []
equity   = INITIAL_CAP
position = None
equity_curve = []

for _, row in df.iterrows():
    # Check stop/target on open position
    if position:
        if position["side"] == "long":
            hit_sl = row["Low"]  <= position["sl"]
            hit_tp = row["High"] >= position["tp"]
        else:
            hit_sl = row["High"] >= position["sl"]
            hit_tp = row["Low"]  <= position["tp"]

        if hit_tp or hit_sl:
            exit_px = position["tp"] if hit_tp else position["sl"]
            pnl_pts = (exit_px - position["entry"]) if position["side"] == "long" \
                      else (position["entry"] - exit_px)
            net_pnl = position["size"] * pnl_pts / position["entry"] \
                      - 2 * COMMISSION * position["size"]
            equity += net_pnl
            trades.append({**position,
                "exit_date": row["Date"], "exit": round(exit_px, 2),
                "result": "TP" if hit_tp else "SL",
                "pnl_pts": round(pnl_pts, 2), "net_pnl": round(net_pnl, 2),
                "equity": round(equity, 2)})
            position = None

    # Check for entry signal
    if position is None:
        above = row["Close"] > row["ema_trend"]
        if row["cross_up"]   and above       and row["rsi"] < RSI_OB:
            position = dict(side="long",  entry=row["Close"], entry_date=row["Date"],
                            sl=row["Close"] - row["atr"]*SL_MULT,
                            tp=row["Close"] + row["atr"]*TP_MULT,
                            size=equity * POSITION_PCT)
        elif row["cross_down"] and not above and row["rsi"] > RSI_OS:
            position = dict(side="short", entry=row["Close"], entry_date=row["Date"],
                            sl=row["Close"] + row["atr"]*SL_MULT,
                            tp=row["Close"] - row["atr"]*TP_MULT,
                            size=equity * POSITION_PCT)

    equity_curve.append({"date": row["Date"], "equity": round(equity, 2)})

# Close any open position at end
if position:
    last = df.iloc[-1]
    exit_px = last["Close"]
    pnl_pts = (exit_px - position["entry"]) if position["side"] == "long" \
              else (position["entry"] - exit_px)
    net_pnl = position["size"] * pnl_pts / position["entry"] \
              - 2 * COMMISSION * position["size"]
    equity += net_pnl
    trades.append({**position,
        "exit_date": last["Date"], "exit": round(exit_px, 2),
        "result": "OPEN→closed", "pnl_pts": round(pnl_pts, 2),
        "net_pnl": round(net_pnl, 2), "equity": round(equity, 2)})

# ── REPORT ────────────────────────────────────────────────────────────────────
ec   = pd.Series([e["equity"] for e in equity_curve])
peak = ec.cummax()
mdd  = ((ec - peak) / peak * 100).min()

if not trades:
    print("No trades triggered.")
else:
    dt      = pd.DataFrame(trades)
    wins    = dt[dt["net_pnl"] > 0]
    losses  = dt[dt["net_pnl"] <= 0]
    total   = len(dt)
    wr      = len(wins)/total*100
    net     = dt["net_pnl"].sum()
    gw      = wins["net_pnl"].sum()
    gl      = losses["net_pnl"].sum()
    pf      = gw / abs(gl) if gl else float("inf")
    ret_pct = net / INITIAL_CAP * 100
    start   = df["Date"].iloc[0].strftime("%Y-%m-%d")
    end     = df["Date"].iloc[-1].strftime("%Y-%m-%d")

    sep = "═" * 54
    print(f"\n{sep}")
    print(f"{'  XAU/USD (GCUSD) — 200-Day Backtest Results':^54}")
    print(f"{sep}")
    print(f"  Data source     FMP (Gold Futures — GCUSD)")
    print(f"  Period          {start}  →  {end}")
    print(f"  Bars            {len(df)} trading days")
    print(f"  Strategy        EMA {EMA_FAST}/{EMA_SLOW} cross | EMA {EMA_TREND} trend filter")
    print(f"                  RSI({RSI_LEN}) filter | ATR({ATR_LEN}) stops")
    print(f"  Risk/Reward     SL={SL_MULT}×ATR  TP={TP_MULT}×ATR  (1:{TP_MULT/SL_MULT:.1f})")
    print(f"  Position size   {int(POSITION_PCT*100)}% equity per trade")
    print(f"  Commission      {COMMISSION*100:.2f}% per side")
    print(sep)
    print(f"  Initial capital   ${INITIAL_CAP:>10,.2f}")
    print(f"  Final equity      ${INITIAL_CAP+net:>10,.2f}")
    sign = "+" if net >= 0 else ""
    print(f"  Net profit        {sign}${net:>9,.2f}  ({sign}{ret_pct:.2f}%)")
    print(f"  Max drawdown      {mdd:.2f}%")
    print(f"  Profit factor     {pf:.2f}")
    print(sep)
    print(f"  Total trades      {total}")
    print(f"  Winners           {len(wins)}  ({wr:.1f}%)")
    print(f"  Losers            {len(losses)}  ({100-wr:.1f}%)")
    if len(wins):   print(f"  Avg win           +${wins['net_pnl'].mean():,.2f}")
    if len(losses): print(f"  Avg loss          -${abs(losses['net_pnl'].mean()):,.2f}")
    print(f"  Best trade        +${dt['net_pnl'].max():,.2f}")
    print(f"  Worst trade       -${abs(dt['net_pnl'].min()):,.2f}")
    print(f"  Avg hold (days)   {(dt['exit_date'] - dt['entry_date']).dt.days.mean():.1f}")
    print(sep)
    print(f"\n  {'#':<3} {'Entry Date':<12} {'Exit Date':<12} {'Side':<6} "
          f"{'Entry':>8} {'Exit':>8} {'SL':>8} {'TP':>8} {'Result':<13} {'Net P&L':>9}")
    print(f"  {'─'*3} {'─'*11} {'─'*11} {'─'*5} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*12} {'─'*9}")
    for i, t in enumerate(trades, 1):
        pnl_s = f"+${t['net_pnl']:,.0f}" if t["net_pnl"] >= 0 else f"-${abs(t['net_pnl']):,.0f}"
        ed = t["entry_date"].strftime("%Y-%m-%d")
        xd = t["exit_date"].strftime("%Y-%m-%d")
        print(f"  {i:<3} {ed:<12} {xd:<12} {t['side']:<6} "
              f"{t['entry']:>8.1f} {t['exit']:>8.1f} {t['sl']:>8.1f} {t['tp']:>8.1f} "
              f"{t['result']:<13} {pnl_s:>9}")
    print()
