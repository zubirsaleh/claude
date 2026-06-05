"""Fetches OHLCV data from TradingView via tvdatafeed."""
from __future__ import annotations

import logging
import pandas as pd
from tvdatafeed import TvDatafeed, Interval

logger = logging.getLogger(__name__)

INTERVALS: dict[str, Interval] = {
    "1m":  Interval.in_1_minute,
    "3m":  Interval.in_3_minute,
    "5m":  Interval.in_5_minute,
    "15m": Interval.in_15_minute,
    "30m": Interval.in_30_minute,
    "1h":  Interval.in_1_hour,
    "2h":  Interval.in_2_hour,
    "4h":  Interval.in_4_hour,
    "1d":  Interval.in_daily,
    "1w":  Interval.in_weekly,
    "1M":  Interval.in_monthly,
}

_client: TvDatafeed | None = None


def _get_client(username: str = "", password: str = "") -> TvDatafeed:
    global _client
    if _client is None:
        _client = TvDatafeed(username or None, password or None)
    return _client


def get_ohlcv(
    symbol: str,
    exchange: str = "BINANCE",
    interval: str = "1h",
    bars: int = 100,
    username: str = "",
    password: str = "",
) -> pd.DataFrame:
    """Return a DataFrame with columns: datetime, open, high, low, close, volume."""
    tv = _get_client(username, password)
    iv = INTERVALS.get(interval.lower(), Interval.in_1_hour)
    df = tv.get_hist(symbol=symbol.upper(), exchange=exchange.upper(), interval=iv, n_bars=bars)
    if df is None or df.empty:
        raise ValueError(f"No data for {symbol} on {exchange} ({interval})")
    return df.reset_index()
