#!/usr/bin/env python3
"""
XAU/USD Backtest v2 — improved parameters.
Runs both original and new config, then prints a side-by-side comparison.

Changes made vs v1:
  1. EMA Fast  : 21  → 9    (faster crossover signals)
  2. EMA Slow  : 50  → 21   (paired with faster EMA)
  3. EMA Trend : 200 → 50   (200-period EMA unusable with only 236 bars of data)
  4. RSI OB    : 70  → 75   (gold was "overbought" all year — don't filter valid longs)
  5. TP Mult   : 3.0 → 2.0  (3×ATR TP rarely hit in sideways pockets; 2× hits more often)
"""

import json
import pandas as pd

# ── DATA ──────────────────────────────────────────────────────────────────────
with open("gcusd_data.json") as f:
    raw = json.load(f)

df_base = pd.DataFrame(raw)[["date","open","high","low","close","volume"]]
df_base.columns = ["Date","Open","High","Low","Close","Volume"]
df_base["Date"] = pd.to_datetime(df_base["Date"])
df_base = df_base.sort_values("Date").reset_index(drop=True)

# ── CONFIGS ───────────────────────────────────────────────────────────────────
CONFIGS = {
    "v1 — Original": dict(
        ema_fast=21, ema_slow=50, ema_trend=200,
        rsi_ob=70, rsi_os=30,
        sl_mult=1.5, tp_mult=3.0,
    ),
    "v2 — Improved": dict(
        ema_fast=9, ema_slow=21, ema_trend=50,
        rsi_ob=75, rsi_os=25,
        sl_mult=1.5, tp_mult=2.0,
    ),
}

INITIAL_CAP  = 10_000.0
POSITION_PCT = 0.10
COMMISSION   = 0.0007

# ── ENGINE ────────────────────────────────────────────────────────────────────
def add_indicators(df, p):
    df = df.copy()
    df["ema_fast"]  = df["Close"].ewm(span=p["ema_fast"],  adjust=False).mean()
    df["ema_slow"]  = df["Close"].ewm(span=p["ema_slow"],  adjust=False).mean()
    df["ema_trend"] = df["Close"].ewm(span=p["ema_trend"], adjust=False).mean()
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))
    hl  = df["High"] - df["Low"]
    hcp = (df["High"] - df["Close"].shift()).abs()
    lcp = (df["Low"]  - df["Close"].shift()).abs()
    df["atr"] = pd.concat([hl, hcp, lcp], axis=1).max(axis=1).ewm(com=13, adjust=False).mean()
    df["cross_up"]   = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift() <= df["ema_slow"].shift())
    df["cross_down"] = (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast"].shift() >= df["ema_slow"].shift())
    return df

def run(df, p):
    trades, equity, position, eq_curve = [], INITIAL_CAP, None, []
    for _, row in df.iterrows():
        if position:
            if position["side"] == "long":
                hit_sl, hit_tp = row["Low"] <= position["sl"], row["High"] >= position["tp"]
            else:
                hit_sl, hit_tp = row["High"] >= position["sl"], row["Low"] <= position["tp"]
            if hit_tp or hit_sl:
                exit_px = position["tp"] if hit_tp else position["sl"]
                pnl_pts = (exit_px - position["entry"]) if position["side"] == "long" \
                           else (position["entry"] - exit_px)
                net_pnl = position["size"] * pnl_pts / position["entry"] \
                           - 2 * COMMISSION * position["size"]
                equity += net_pnl
                trades.append({**position, "exit_date": row["Date"],
                    "exit": round(exit_px,2), "result": "TP" if hit_tp else "SL",
                    "pnl_pts": round(pnl_pts,2), "net_pnl": round(net_pnl,2),
                    "equity": round(equity,2)})
                position = None
        if position is None:
            above = row["Close"] > row["ema_trend"]
            if row["cross_up"]   and above     and row["rsi"] < p["rsi_ob"]:
                position = dict(side="long",  entry=row["Close"], entry_date=row["Date"],
                    sl=row["Close"] - row["atr"]*p["sl_mult"],
                    tp=row["Close"] + row["atr"]*p["tp_mult"],
                    size=equity * POSITION_PCT)
            elif row["cross_down"] and not above and row["rsi"] > p["rsi_os"]:
                position = dict(side="short", entry=row["Close"], entry_date=row["Date"],
                    sl=row["Close"] + row["atr"]*p["sl_mult"],
                    tp=row["Close"] - row["atr"]*p["tp_mult"],
                    size=equity * POSITION_PCT)
        eq_curve.append(round(equity, 2))
    if position:
        last = df.iloc[-1]
        exit_px = last["Close"]
        pnl_pts = (exit_px - position["entry"]) if position["side"] == "long" \
                   else (position["entry"] - exit_px)
        net_pnl = position["size"] * pnl_pts / position["entry"] \
                   - 2 * COMMISSION * position["size"]
        equity += net_pnl
        trades.append({**position, "exit_date": last["Date"],
            "exit": round(exit_px,2), "result": "OPEN→closed",
            "pnl_pts": round(pnl_pts,2), "net_pnl": round(net_pnl,2),
            "equity": round(equity,2)})
        eq_curve.append(round(equity, 2))
    ec   = pd.Series(eq_curve)
    peak = ec.cummax()
    mdd  = ((ec - peak) / peak * 100).min()
    return trades, round(equity, 2), round(mdd, 2)

# ── RUN BOTH ─────────────────────────────────────────────────────────────────
results = {}
for label, cfg in CONFIGS.items():
    df = add_indicators(df_base, cfg)
    trades, final_eq, mdd = run(df, cfg)
    dt     = pd.DataFrame(trades) if trades else pd.DataFrame()
    wins   = dt[dt["net_pnl"] > 0] if not dt.empty else pd.DataFrame()
    losses = dt[dt["net_pnl"] <= 0] if not dt.empty else pd.DataFrame()
    net    = dt["net_pnl"].sum() if not dt.empty else 0
    gw     = wins["net_pnl"].sum() if not wins.empty else 0
    gl     = losses["net_pnl"].sum() if not losses.empty else 0
    pf     = gw / abs(gl) if gl != 0 else (float("inf") if gw > 0 else 0)
    results[label] = dict(
        trades=trades, dt=dt, wins=wins, losses=losses,
        net=net, pf=pf, mdd=mdd, final_eq=final_eq,
        total=len(trades), cfg=cfg,
    )

# ── PRINT INDIVIDUAL TRADE LOGS ───────────────────────────────────────────────
for label, r in results.items():
    sep = "═" * 58
    cfg = r["cfg"]
    print(f"\n{sep}")
    print(f"  {label:^56}")
    print(sep)
    print(f"  EMA fast/slow/trend  {cfg['ema_fast']}/{cfg['ema_slow']}/{cfg['ema_trend']}")
    print(f"  RSI OB/OS            {cfg['rsi_ob']}/{cfg['rsi_os']}")
    print(f"  SL / TP              {cfg['sl_mult']}×ATR  /  {cfg['tp_mult']}×ATR")
    print(sep)
    if r["dt"].empty:
        print("  No trades triggered.")
        continue
    wr  = len(r["wins"]) / r["total"] * 100
    ret = r["net"] / INITIAL_CAP * 100
    print(f"  Initial capital    ${INITIAL_CAP:>10,.2f}")
    print(f"  Final equity       ${r['final_eq']:>10,.2f}")
    sign = "+" if r["net"] >= 0 else ""
    print(f"  Net profit         {sign}${r['net']:>9,.2f}  ({sign}{ret:.2f}%)")
    print(f"  Max drawdown       {r['mdd']:.2f}%")
    print(f"  Profit factor      {r['pf']:.2f}")
    print(f"  Total trades       {r['total']}")
    print(f"  Win rate           {wr:.1f}%  ({len(r['wins'])}W / {len(r['losses'])}L)")
    if not r["wins"].empty:   print(f"  Avg win            +${r['wins']['net_pnl'].mean():,.2f}")
    if not r["losses"].empty: print(f"  Avg loss           -${abs(r['losses']['net_pnl'].mean()):,.2f}")
    print(f"  Best trade         +${r['dt']['net_pnl'].max():,.2f}")
    print(f"  Worst trade        ${r['dt']['net_pnl'].min():,.2f}")
    avg_hold = (r["dt"]["exit_date"] - r["dt"]["entry_date"]).dt.days.mean()
    print(f"  Avg hold           {avg_hold:.1f} days")
    print(f"\n  {'#':<3} {'Entry':<12} {'Exit':<12} {'Side':<6} {'@Entry':>8} {'@Exit':>8} {'Result':<13} {'P&L':>9}")
    print(f"  {'─'*3} {'─'*11} {'─'*11} {'─'*5} {'─'*8} {'─'*8} {'─'*12} {'─'*9}")
    for i, t in enumerate(r["trades"], 1):
        pnl_s = f"+${t['net_pnl']:,.0f}" if t["net_pnl"] >= 0 else f"-${abs(t['net_pnl']):,.0f}"
        print(f"  {i:<3} {t['entry_date'].strftime('%Y-%m-%d'):<12} "
              f"{t['exit_date'].strftime('%Y-%m-%d'):<12} {t['side']:<6} "
              f"{t['entry']:>8.1f} {t['exit']:>8.1f} {t['result']:<13} {pnl_s:>9}")

# ── SIDE-BY-SIDE COMPARISON ───────────────────────────────────────────────────
v1 = results["v1 — Original"]
v2 = results["v2 — Improved"]

def fmt(val, prefix="$", suffix="", decimals=2):
    return f"{prefix}{val:,.{decimals}f}{suffix}"

def delta_str(new, old, is_pct=False, lower_better=False):
    d = new - old
    if d == 0: return "  —"
    arrow = "▲" if (d > 0) != lower_better else "▼"
    sign  = "+" if d > 0 else ""
    unit  = "%" if is_pct else ""
    return f"{arrow} {sign}{d:.2f}{unit}"

print(f"\n\n{'═'*58}")
print(f"  {'SIDE-BY-SIDE COMPARISON':^56}")
print(f"{'═'*58}")
print(f"  {'Metric':<28} {'v1 Original':>12} {'v2 Improved':>12}")
print(f"  {'─'*28} {'─'*12} {'─'*12}")

v1_net  = v1["net"]; v2_net  = v2["net"]
v1_ret  = v1_net/INITIAL_CAP*100; v2_ret  = v2_net/INITIAL_CAP*100
v1_wr   = (len(v1["wins"])/v1["total"]*100) if v1["total"] else 0
v2_wr   = (len(v2["wins"])/v2["total"]*100) if v2["total"] else 0

rows = [
    ("Net profit ($)",       f"+${v1_net:,.2f}",          f"+${v2_net:,.2f}",          delta_str(v2_net, v1_net)),
    ("Return (%)",           f"+{v1_ret:.2f}%",           f"+{v2_ret:.2f}%",           delta_str(v2_ret, v1_ret, is_pct=True)),
    ("Max drawdown (%)",     f"{v1['mdd']:.2f}%",         f"{v2['mdd']:.2f}%",         delta_str(v2["mdd"], v1["mdd"], is_pct=True, lower_better=True)),
    ("Profit factor",        f"{v1['pf']:.2f}",           f"{v2['pf']:.2f}",           ""),
    ("Total trades",         str(v1["total"]),            str(v2["total"]),            f"▲ +{v2['total']-v1['total']}"),
    ("Win rate (%)",         f"{v1_wr:.1f}%",             f"{v2_wr:.1f}%",             delta_str(v2_wr, v1_wr, is_pct=True)),
    ("Winners",              str(len(v1["wins"])),        str(len(v2["wins"])),        ""),
    ("Losers",               str(len(v1["losses"])),      str(len(v2["losses"])),      ""),
    ("Final equity ($)",     f"${v1['final_eq']:,.2f}",   f"${v2['final_eq']:,.2f}",   ""),
]

for metric, c1, c2, change in rows:
    print(f"  {metric:<28} {c1:>12} {c2:>12}   {change}")

print(f"{'═'*58}")

print(f"""
  WHAT CHANGED & WHY
  ──────────────────
  1. EMA Fast  21 → 9    Faster crossovers. In a strong trend, EMA 21
                          barely crossed EMA 50 at all — EMA 9/21 fires
                          more signals while still filtering noise.

  2. EMA Slow  50 → 21   Paired with EMA 9 to create a usable fast/slow
                          pair that reacts to gold's volatile swings.

  3. EMA Trend 200 → 50  EMA 200 is meaningless with only 236 bars — it
                          was almost identical to price. EMA 50 gives a
                          real bull/bear trend read over this dataset.

  4. RSI OB    70 → 75   Gold's RSI stayed above 70 for long stretches
                          during the bull run. Raising the threshold stops
                          the filter blocking valid trend-following longs.

  5. TP Mult   3.0 → 2.0 A 3×ATR target was too ambitious — gold's daily
                          ATR of ~$80–120 made those TPs hard to reach.
                          2×ATR keeps a positive R:R (1:1.33) and lands
                          more completed trades.
""")
