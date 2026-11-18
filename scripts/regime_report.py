"""Regime and signal-frequency report on stored XAUUSD 1M bars.

Reports label distribution, how often the regime label held over the next 60 minutes,
and how many signals each strategy produces (and how many the USD 400 risk cap rejects).
It deliberately reports no P&L: that needs walk-forward testing on months of data.

    python scripts/regime_report.py [--store data/xauusd_m1]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scalper.data import BarStore  # noqa: E402
from scalper.features import build_features  # noqa: E402
from scalper.regime import classify, confusion, forward_truth  # noqa: E402
from scalper.settings import LIMITS  # noqa: E402
from scalper.strategies import STRATEGIES, generate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="data/xauusd_m1")
    args = ap.parse_args()

    bars = BarStore(Path(args.store)).load()
    if bars.empty:
        print("no bars stored")
        return 1
    f = build_features(bars)
    regime = classify(f)
    days = f["tday"].nunique()
    print(f"bars {len(f)}  {f.index.min()} -> {f.index.max()}  trading days {days}")

    print("\nRegime share by session (%):")
    print((pd.crosstab(f["session"], regime, normalize="index") * 100).round(1).to_string())

    table, wrong = confusion(regime, forward_truth(f))
    print(f"\nRegime label vs what the next 60 min did (rows = predicted):\n{table.to_string()}")
    print(f"label did not hold over the next 60 min: {wrong:.1%}")

    print("\nSignals (regime- and session-gated):")
    rows = []
    for name in STRATEGIES:
        sig = generate(f, regime, name)
        on = sig[sig["side"] != 0]
        risk = (f.loc[on.index, "close"] - on["stop"]).abs() * LIMITS.units
        rows.append({
            "strategy": name,
            "signals": len(on),
            "per_day": round(len(on) / max(days, 1), 2),
            "median_stop_usd": round(float((risk / LIMITS.units).median()), 2) if len(on) else None,
            "median_risk_usd": round(float(risk.median()), 0) if len(on) else None,
            "over_400_cap": int((risk > LIMITS.max_risk_per_trade_usd).sum()),
            "by_session": on.index.map(f["session"]).value_counts().to_dict(),
        })
    print(pd.DataFrame(rows).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
