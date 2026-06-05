"""Candlestick pattern detection using pandas-ta."""
from __future__ import annotations

import logging
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

_PATTERNS = [
    "doji", "hammer", "invertedhammer", "shootingstar",
    "engulfing", "morningstar", "eveningstar",
    "3whitesoldiers", "3blackcrows", "harami",
    "haramicross", "piercingline", "darkcloudcover",
    "dragonflydoji", "gravestonedoji", "spinningtop",
    "marubozu",
]

_READABLE: dict[str, str] = {
    "doji": "Doji",
    "hammer": "Hammer",
    "invertedhammer": "Inverted Hammer",
    "shootingstar": "Shooting Star",
    "engulfing": "Engulfing",
    "morningstar": "Morning Star",
    "eveningstar": "Evening Star",
    "3whitesoldiers": "Three White Soldiers",
    "3blackcrows": "Three Black Crows",
    "harami": "Harami",
    "haramicross": "Harami Cross",
    "piercingline": "Piercing Line",
    "darkcloudcover": "Dark Cloud Cover",
    "dragonflydoji": "Dragonfly Doji",
    "gravestonedoji": "Gravestone Doji",
    "spinningtop": "Spinning Top",
    "marubozu": "Marubozu",
}


def detect_patterns(df: pd.DataFrame, last_n: int = 5) -> list[dict]:
    """
    Scan the last `last_n` candles for candlestick patterns.
    Returns a list of {pattern, signal, candle_time} dicts.
    """
    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        return []

    # Give context rows for multi-candle patterns
    tail = df.tail(last_n + 15).copy()
    found: list[dict] = []

    for name in _PATTERNS:
        try:
            result = ta.cdl_pattern(
                tail["open"], tail["high"], tail["low"], tail["close"], name=name
            )
            if result is None or result.empty:
                continue
            for col in result.columns:
                active = result[col][result[col] != 0].tail(last_n)
                for idx, val in active.items():
                    time_label = str(idx)
                    if "datetime" in tail.columns:
                        matched = tail[tail.index == idx]
                        if not matched.empty and "datetime" in matched.columns:
                            time_label = str(matched["datetime"].iloc[0])
                    found.append(
                        {
                            "pattern": _READABLE.get(name, name.replace("_", " ").title()),
                            "signal": "bullish" if val > 0 else "bearish",
                            "candle_time": time_label,
                        }
                    )
        except Exception as exc:
            logger.debug("Pattern %s failed: %s", name, exc)

    return found
