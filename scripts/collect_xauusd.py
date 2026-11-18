"""Pull the latest XAUUSD 1M bars from TradingView and merge them into the local store.

TradingView serves at most ~5,000 1M bars (about 3.5 trading days) per request, so run
this at least every 2 days (e.g. cron) to build continuous history.

    python scripts/collect_xauusd.py [--symbol XAUUSD --exchange OANDA --store data/xauusd_m1]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scalper.data import BarStore, normalize_tv_bars, quality_report  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--exchange", default="OANDA")
    ap.add_argument("--store", default="data/xauusd_m1")
    ap.add_argument("--bars", type=int, default=5000)
    args = ap.parse_args()

    # tvdatafeed builds naive timestamps in process-local time; pin it to UTC.
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()
        local_tz = "UTC"
    else:
        from tzlocal import get_localzone_name  # Windows has no tzset
        local_tz = get_localzone_name()

    from trading.fetcher import get_ohlcv

    raw = get_ohlcv(args.symbol, args.exchange, "1m", args.bars,
                    os.getenv("TRADINGVIEW_USERNAME", ""), os.getenv("TRADINGVIEW_PASSWORD", ""))
    bars = normalize_tv_bars(raw, local_tz)
    store = BarStore(Path(args.store))
    result = store.merge(bars)
    print(f"fetched {len(bars)} closed bars {bars.index.min()} -> {bars.index.max()}")
    print(f"added {result['added']}, revised {result['revised']}")
    print(quality_report(store.load()).as_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
