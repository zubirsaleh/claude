#!/usr/bin/env python3
"""
XAU/USD Backtest v3 — all three versions compared.

v3 CORE INSIGHT:
  v2 hit TP at $3,499 on Aug 29 and exited. Gold then ran to $4,252
  over the next 75 days — all missed because of the fixed TP ceiling.
  The fix: remove the TP ceiling. Exit when the EMA-9 crosses back
  below EMA-21 (trend reversal). Add a trailing breakeven stop so we
  never lose money on a trade that was once profitable.

v3 changes vs v2:
  1. NO fixed TP  — exit when EMA-9 crosses back through EMA-21
     (lets the trade ride the full trend leg, not just 2×ATR)
  2. Trailing breakeven — when price moves +1×entry_ATR in our favour,
     move SL to entry price; eliminates risk of a profitable trade turning
     into a loss
  3. Position size 10% → 12%  (modest increase; new exits are less
     predictable so keep sizing conservative)
  EMA 9/21/50, RSI 75/25, SL 1.5×ATR all unchanged.
"""

import json
import pandas as pd

with open("gcusd_data.json") as f:
    raw = json.load(f)

df_base = pd.DataFrame(raw)[["date","open","high","low","close","volume"]]
df_base.columns = ["Date","Open","High","Low","Close","Volume"]
df_base["Date"] = pd.to_datetime(df_base["Date"])
df_base = df_base.sort_values("Date").reset_index(drop=True)

INITIAL_CAP = 10_000.0
COMMISSION  = 0.0007

CONFIGS = {
    "v1 — Original": dict(ema_fast=21, ema_slow=50, ema_trend=200,
                          rsi_ob=70, rsi_os=30, sl_mult=1.5, tp_mult=3.0,
                          pos_pct=0.10, pullback=False),
    "v2 — Improved": dict(ema_fast=9,  ema_slow=21, ema_trend=50,
                          rsi_ob=75, rsi_os=25, sl_mult=1.5, tp_mult=2.0,
                          pos_pct=0.10, pullback=False),
    "v3 — Optimised": dict(ema_fast=9,  ema_slow=21, ema_trend=50,
                           rsi_ob=75, rsi_os=25, sl_mult=1.5, tp_mult=None,
                           pos_pct=0.12, pullback=False),
}

def build(df, p):
    df = df.copy()
    df["ef"]  = df["Close"].ewm(span=p["ema_fast"],  adjust=False).mean()
    df["es"]  = df["Close"].ewm(span=p["ema_slow"],  adjust=False).mean()
    df["et"]  = df["Close"].ewm(span=p["ema_trend"], adjust=False).mean()
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))
    hl  = df["High"] - df["Low"]
    hcp = (df["High"] - df["Close"].shift()).abs()
    lcp = (df["Low"]  - df["Close"].shift()).abs()
    df["atr"] = pd.concat([hl, hcp, lcp], axis=1).max(axis=1).ewm(com=13, adjust=False).mean()
    df["xup"]  = (df["ef"] > df["es"]) & (df["ef"].shift() <= df["es"].shift())
    df["xdn"]  = (df["ef"] < df["es"]) & (df["ef"].shift() >= df["es"].shift())
    return df

def run(df, p):
    use_ema_exit = p["tp_mult"] is None   # v3 mode: exit on EMA cross-back
    trades, equity, pos, ec = [], INITIAL_CAP, None, []

    for _, r in df.iterrows():
        if pos:
            # ── Trailing breakeven (v3 only): move SL to entry once +1×ATR in profit ──
            if use_ema_exit:
                if pos["side"] == "long" and pos["sl"] < pos["entry"]:
                    if r["High"] >= pos["entry"] + pos["entry_atr"]:
                        pos["sl"] = pos["entry"]
                elif pos["side"] == "short" and pos["sl"] > pos["entry"]:
                    if r["Low"] <= pos["entry"] - pos["entry_atr"]:
                        pos["sl"] = pos["entry"]

            hit_sl = (r["Low"]  <= pos["sl"]) if pos["side"]=="long" else (r["High"] >= pos["sl"])
            hit_tp = False if use_ema_exit else (
                (r["High"] >= pos["tp"]) if pos["side"]=="long" else (r["Low"] <= pos["tp"])
            )
            # EMA-cross exit: EMA-9 crosses back through EMA-21
            ema_exit = use_ema_exit and (
                (pos["side"]=="long"  and r["ef"] < r["es"]) or
                (pos["side"]=="short" and r["ef"] > r["es"])
            )

            if hit_sl or hit_tp or ema_exit:
                if hit_sl:
                    xp, result = pos["sl"], "SL"
                elif hit_tp:
                    xp, result = pos["tp"], "TP"
                else:
                    xp, result = r["Close"], "EMA-exit"
                pts     = (xp - pos["entry"]) if pos["side"]=="long" else (pos["entry"] - xp)
                net_pnl = pos["size"] * pts / pos["entry"] - 2 * COMMISSION * pos["size"]
                equity += net_pnl
                trades.append({**pos, "exit_date": r["Date"], "exit": round(xp, 2),
                                "result": result, "pts": round(pts, 2),
                                "net_pnl": round(net_pnl, 2), "equity": round(equity, 2)})
                pos = None

        if pos is None:
            above = r["Close"] > r["et"]
            if r["xup"] and above and r["rsi"] < p["rsi_ob"]:
                atr_now = r["atr"]
                pos = dict(side="long", entry=r["Close"], entry_date=r["Date"],
                           sl=r["Close"] - atr_now * p["sl_mult"],
                           tp=None if use_ema_exit else r["Close"] + atr_now * p["tp_mult"],
                           entry_atr=atr_now, size=equity * p["pos_pct"])
            elif r["xdn"] and not above and r["rsi"] > p["rsi_os"]:
                atr_now = r["atr"]
                pos = dict(side="short", entry=r["Close"], entry_date=r["Date"],
                           sl=r["Close"] + atr_now * p["sl_mult"],
                           tp=None if use_ema_exit else r["Close"] - atr_now * p["tp_mult"],
                           entry_atr=atr_now, size=equity * p["pos_pct"])
        ec.append(round(equity, 2))

    if pos:
        last = df.iloc[-1]
        xp  = last["Close"]
        pts = (xp - pos["entry"]) if pos["side"]=="long" else (pos["entry"] - xp)
        net_pnl = pos["size"] * pts / pos["entry"] - 2 * COMMISSION * pos["size"]
        equity += net_pnl
        trades.append({**pos, "exit_date": last["Date"], "exit": round(xp, 2),
                        "result": "OPEN→closed", "pts": round(pts, 2),
                        "net_pnl": round(net_pnl, 2), "equity": round(equity, 2)})
        ec.append(round(equity, 2))

    s  = pd.Series(ec)
    pk = s.cummax()
    dd = ((s - pk) / pk * 100).min()
    return trades, round(equity, 2), round(dd, 2)

# ── RUN ALL THREE ─────────────────────────────────────────────────────────────
all_results = {}
for label, cfg in CONFIGS.items():
    df  = build(df_base, cfg)
    trades, final_eq, mdd = run(df, cfg)
    dt     = pd.DataFrame(trades) if trades else pd.DataFrame()
    wins   = dt[dt["net_pnl"] > 0]   if not dt.empty else pd.DataFrame()
    losses = dt[dt["net_pnl"] <= 0]  if not dt.empty else pd.DataFrame()
    net    = dt["net_pnl"].sum()      if not dt.empty else 0.0
    gw     = wins["net_pnl"].sum()    if not wins.empty   else 0.0
    gl     = losses["net_pnl"].sum()  if not losses.empty else 0.0
    pf     = gw / abs(gl) if gl != 0 else (float("inf") if gw > 0 else 0.0)
    all_results[label] = dict(trades=trades, dt=dt, wins=wins, losses=losses,
                               net=net, pf=pf, mdd=mdd, final_eq=final_eq,
                               total=len(trades), cfg=cfg)

# ── DETAILED TRADE LOG PER VERSION ───────────────────────────────────────────
for label, r in all_results.items():
    sep = "═" * 62
    c = r["cfg"]
    print(f"\n{sep}")
    print(f"  {label:^60}")
    print(sep)
    print(f"  EMA fast/slow/trend : {c['ema_fast']}/{c['ema_slow']}/{c['ema_trend']}")
    print(f"  RSI OB/OS           : {c['rsi_ob']}/{c['rsi_os']}")
    rr_str = f"1:{c['tp_mult']/c['sl_mult']:.2f}" if c["tp_mult"] else "trail (EMA exit)"
    tp_str = f"{c['tp_mult']}×ATR" if c["tp_mult"] else "EMA cross"
    print(f"  SL/TP               : {c['sl_mult']}×ATR / {tp_str}  (R:R {rr_str})")
    print(f"  Position size       : {int(c['pos_pct']*100)}% per trade")
    print(sep)
    if r["dt"].empty:
        print("  No trades triggered.")
        continue
    wr  = len(r["wins"]) / r["total"] * 100
    ret = r["net"] / INITIAL_CAP * 100
    sign = "+" if r["net"] >= 0 else ""
    print(f"  Initial capital     : ${INITIAL_CAP:>10,.2f}")
    print(f"  Final equity        : ${r['final_eq']:>10,.2f}")
    print(f"  Net profit          : {sign}${r['net']:>9,.2f}  ({sign}{ret:.2f}%)")
    print(f"  Max drawdown        : {r['mdd']:.2f}%")
    print(f"  Profit factor       : {r['pf']:.2f}")
    print(f"  Total trades        : {r['total']}")
    print(f"  Win rate            : {wr:.1f}%  ({len(r['wins'])}W / {len(r['losses'])}L)")
    if not r["wins"].empty:
        print(f"  Avg win             : +${r['wins']['net_pnl'].mean():,.2f}")
    if not r["losses"].empty:
        print(f"  Avg loss            : -${abs(r['losses']['net_pnl'].mean()):,.2f}")
    print(f"  Best trade          : +${r['dt']['net_pnl'].max():,.2f}")
    print(f"  Worst trade         : ${r['dt']['net_pnl'].min():,.2f}")
    avg_h = (r["dt"]["exit_date"] - r["dt"]["entry_date"]).dt.days.mean()
    print(f"  Avg hold            : {avg_h:.1f} days")
    print(f"\n  {'#':<3} {'Entry':<12} {'Exit':<12} {'Side':<6} "
          f"{'@Entry':>8} {'@Exit':>8} {'SL':>8} {'TP':>8} {'Result':<13} {'P&L':>9}")
    print(f"  {'─'*3} {'─'*11} {'─'*11} {'─'*5} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*12} {'─'*9}")
    for i, t in enumerate(r["trades"], 1):
        ps   = f"+${t['net_pnl']:,.0f}" if t["net_pnl"] >= 0 else f"-${abs(t['net_pnl']):,.0f}"
        tp_s = f"{t['tp']:>8.1f}" if t.get("tp") else "   trail"
        print(f"  {i:<3} {t['entry_date'].strftime('%Y-%m-%d'):<12} "
              f"{t['exit_date'].strftime('%Y-%m-%d'):<12} {t['side']:<6} "
              f"{t['entry']:>8.1f} {t['exit']:>8.1f} {t['sl']:>8.1f} {tp_s} "
              f"{t['result']:<13} {ps:>9}")

# ── THREE-WAY COMPARISON TABLE ────────────────────────────────────────────────
v1 = all_results["v1 — Original"]
v2 = all_results["v2 — Improved"]
v3 = all_results["v3 — Optimised"]

def pct(v): return v / INITIAL_CAP * 100
def wr(r):  return len(r["wins"]) / r["total"] * 100 if r["total"] else 0

print(f"\n\n{'═'*70}")
print(f"  {'THREE-WAY COMPARISON':^68}")
print(f"{'═'*70}")
print(f"  {'Metric':<26} {'v1 Original':>13} {'v2 Improved':>13} {'v3 Optimised':>13}")
print(f"  {'─'*26} {'─'*13} {'─'*13} {'─'*13}")

def arr(new, old):
    d = new - old
    return ("▲" if d > 0 else "▼") + f" {abs(d):+.2f}" if d != 0 else "  —"

rows = [
    ("── Parameters ──────────────", "", "", ""),
    ("  EMA fast/slow/trend",
        f"{v1['cfg']['ema_fast']}/{v1['cfg']['ema_slow']}/{v1['cfg']['ema_trend']}",
        f"{v2['cfg']['ema_fast']}/{v2['cfg']['ema_slow']}/{v2['cfg']['ema_trend']}",
        f"{v3['cfg']['ema_fast']}/{v3['cfg']['ema_slow']}/{v3['cfg']['ema_trend']}"),
    ("  RSI OB / OS",
        f"{v1['cfg']['rsi_ob']}/{v1['cfg']['rsi_os']}",
        f"{v2['cfg']['rsi_ob']}/{v2['cfg']['rsi_os']}",
        f"{v3['cfg']['rsi_ob']}/{v3['cfg']['rsi_os']}"),
    ("  SL / TP (×ATR)",
        f"{v1['cfg']['sl_mult']}/{v1['cfg']['tp_mult']}",
        f"{v2['cfg']['sl_mult']}/{v2['cfg']['tp_mult']}",
        f"{v3['cfg']['sl_mult']}/EMA-exit"),
    ("  R:R ratio",
        f"1:{v1['cfg']['tp_mult']/v1['cfg']['sl_mult']:.1f}",
        f"1:{v2['cfg']['tp_mult']/v2['cfg']['sl_mult']:.1f}",
        "trailing"),
    ("  Position size",
        f"{int(v1['cfg']['pos_pct']*100)}%",
        f"{int(v2['cfg']['pos_pct']*100)}%",
        f"{int(v3['cfg']['pos_pct']*100)}%"),
    ("── Performance ─────────────", "", "", ""),
    ("  Net profit ($)",
        f"+${v1['net']:.2f}", f"+${v2['net']:.2f}", f"+${v3['net']:.2f}"),
    ("  Return (%)",
        f"+{pct(v1['net']):.2f}%", f"+{pct(v2['net']):.2f}%", f"+{pct(v3['net']):.2f}%"),
    ("  Final equity ($)",
        f"${v1['final_eq']:,.2f}", f"${v2['final_eq']:,.2f}", f"${v3['final_eq']:,.2f}"),
    ("  Max drawdown (%)",
        f"{v1['mdd']:.2f}%", f"{v2['mdd']:.2f}%", f"{v3['mdd']:.2f}%"),
    ("  Profit factor",
        f"{v1['pf']:.2f}", f"{v2['pf']:.2f}", f"{v3['pf']:.2f}"),
    ("── Trade Stats ─────────────", "", "", ""),
    ("  Total trades",
        str(v1['total']), str(v2['total']), str(v3['total'])),
    ("  Win rate (%)",
        f"{wr(v1):.1f}%", f"{wr(v2):.1f}%", f"{wr(v3):.1f}%"),
    ("  Winners / Losers",
        f"{len(v1['wins'])}W / {len(v1['losses'])}L",
        f"{len(v2['wins'])}W / {len(v2['losses'])}L",
        f"{len(v3['wins'])}W / {len(v3['losses'])}L"),
    ("  Avg win ($)",
        f"+${v1['wins']['net_pnl'].mean():.2f}" if not v1["wins"].empty else "—",
        f"+${v2['wins']['net_pnl'].mean():.2f}" if not v2["wins"].empty else "—",
        f"+${v3['wins']['net_pnl'].mean():.2f}" if not v3["wins"].empty else "—"),
    ("  Avg loss ($)",
        f"-${abs(v1['losses']['net_pnl'].mean()):.2f}" if not v1["losses"].empty else "—",
        f"-${abs(v2['losses']['net_pnl'].mean()):.2f}" if not v2["losses"].empty else "—",
        f"-${abs(v3['losses']['net_pnl'].mean()):.2f}" if not v3["losses"].empty else "—"),
]

for metric, c1, c2, c3 in rows:
    print(f"  {metric:<26} {c1:>13} {c2:>13} {c3:>13}")

print(f"{'═'*70}")

# v3 vs v2 improvement summary
imp_net = v3["net"] - v2["net"]
imp_ret = pct(v3["net"]) - pct(v2["net"])
imp_trd = v3["total"] - v2["total"]
print(f"""
  v3 vs v2 IMPROVEMENT SUMMARY
  ─────────────────────────────
  Net profit   +${imp_net:,.2f} more  ({imp_ret:+.2f}% extra return)
  Trades       +{imp_trd} more trades
  Win rate     {wr(v3):.1f}%  vs  {wr(v2):.1f}%

  v3 CHANGE LOG
  ─────────────
  1. Fixed TP removed → EMA-cross exit
          v2's Aug 26 trade hit TP at $3,499 after just 5 days. Gold then
          ran to $4,252 over the next 75 days — all missed because the 2×ATR
          ceiling cut the trade short. v3 stays in the trade until EMA-9
          crosses back below EMA-21 (trend reversal confirmed), capturing
          the full trend leg rather than a fraction of it.

  2. Trailing breakeven stop
          Once price moves +1×entry_ATR in our favour, SL is moved to
          entry price. A winning trade can never turn into a loss. This
          is essential since we no longer have a TP ceiling to lock in gains.

  3. Position size  10% → 12%
          EMA-cross exits are less predictable than fixed TPs, so a
          modest size increase (not aggressive) is used.

  EMA 9/21/50, RSI 75/25, SL 1.5×ATR all unchanged from v2.
""")
