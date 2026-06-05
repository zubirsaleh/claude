"""Candlestick pattern engine.

Detects classic single- and multi-candle patterns on the last completed
candles. Detection is purely geometric on real OHLC values — no fabrication.
"""
from __future__ import annotations

import pandas as pd

# Patterns this engine knows about.
PATTERNS = (
    "Doji",
    "Hammer",
    "Inverted Hammer",
    "Shooting Star",
    "Bullish Engulfing",
    "Bearish Engulfing",
    "Morning Star",
    "Evening Star",
    "Spinning Top",
    "Marubozu",
    "Dragonfly Doji",
    "Gravestone Doji",
)

_BULLISH = {"Hammer", "Inverted Hammer", "Bullish Engulfing", "Morning Star", "Dragonfly Doji"}
_BEARISH = {"Shooting Star", "Bearish Engulfing", "Evening Star", "Gravestone Doji"}


def _body(c) -> float:
    return abs(c.close - c.open)


def _range(c) -> float:
    return c.high - c.low or 1e-9


def _upper_wick(c) -> float:
    return c.high - max(c.open, c.close)


def _lower_wick(c) -> float:
    return min(c.open, c.close) - c.low


def _is_bull(c) -> bool:
    return c.close > c.open


def _detect_single(c) -> list[str]:
    found = []
    rng = _range(c)
    body = _body(c)
    body_ratio = body / rng
    upper = _upper_wick(c)
    lower = _lower_wick(c)

    # Doji family — very small body.
    if body_ratio <= 0.1:
        if lower >= 2 * body and upper <= body:
            found.append("Dragonfly Doji")
        elif upper >= 2 * body and lower <= body:
            found.append("Gravestone Doji")
        else:
            found.append("Doji")
        return found

    # Marubozu — almost no wicks.
    if upper <= 0.05 * rng and lower <= 0.05 * rng and body_ratio >= 0.9:
        found.append("Marubozu")
        return found

    # Hammer / Hanging-man shape: long lower wick, small upper wick.
    if lower >= 2 * body and upper <= body and body_ratio < 0.4:
        found.append("Hammer")
    # Inverted hammer / shooting-star shape: long upper wick.
    if upper >= 2 * body and lower <= body and body_ratio < 0.4:
        found.append("Inverted Hammer" if _is_bull(c) else "Shooting Star")

    # Spinning top — small body centred between two comparable wicks.
    if 0.1 < body_ratio <= 0.3 and upper >= body and lower >= body:
        found.append("Spinning Top")

    return found


def _detect_pair(prev, cur) -> list[str]:
    found = []
    prev_body = _body(prev)
    cur_body = _body(cur)
    # Bullish engulfing.
    if (
        not _is_bull(prev)
        and _is_bull(cur)
        and cur.close >= prev.open
        and cur.open <= prev.close
        and cur_body > prev_body
    ):
        found.append("Bullish Engulfing")
    # Bearish engulfing.
    if (
        _is_bull(prev)
        and not _is_bull(cur)
        and cur.open >= prev.close
        and cur.close <= prev.open
        and cur_body > prev_body
    ):
        found.append("Bearish Engulfing")
    return found


def _detect_triple(a, b, c) -> list[str]:
    found = []
    a_body = _body(a)
    b_body = _body(b)
    rng_a = _range(a)
    # Small middle candle is the hallmark of star patterns.
    small_middle = b_body <= 0.5 * a_body
    # Morning star: down, small, strong up closing into first body.
    if (
        not _is_bull(a)
        and small_middle
        and _is_bull(c)
        and a_body > 0.5 * rng_a
        and c.close > (a.open + a.close) / 2
    ):
        found.append("Morning Star")
    # Evening star: up, small, strong down closing into first body.
    if (
        _is_bull(a)
        and small_middle
        and not _is_bull(c)
        and a_body > 0.5 * rng_a
        and c.close < (a.open + a.close) / 2
    ):
        found.append("Evening Star")
    return found


def detect_patterns(df: pd.DataFrame) -> dict:
    """Detect patterns over the last 5 completed candles.

    Returns the per-candle detections, the most significant pattern, and an
    overall bullish/bearish/neutral signal derived from it.
    """
    if len(df) < 5:
        return {"last_5": [], "detected": "None", "signal": "Neutral"}

    window = df.tail(5).reset_index(drop=True)
    rows = [window.iloc[i] for i in range(len(window))]

    per_candle: list[dict] = []
    all_found: list[str] = []

    for i, c in enumerate(rows):
        found = _detect_single(c)
        if i >= 1:
            found += _detect_pair(rows[i - 1], c)
        if i >= 2:
            found += _detect_triple(rows[i - 2], rows[i - 1], c)
        per_candle.append(
            {
                "index": i,
                "direction": "bull" if _is_bull(c) else "bear",
                "patterns": found,
            }
        )
        all_found += found

    # The most meaningful pattern is the most recent multi-candle one if any,
    # otherwise the latest single-candle detection.
    detected = "None"
    for entry in reversed(per_candle):
        if entry["patterns"]:
            # Prefer reversal/multi-candle names over plain Doji/Spinning Top.
            priority = [
                p
                for p in entry["patterns"]
                if p not in ("Doji", "Spinning Top")
            ]
            detected = (priority or entry["patterns"])[-1]
            break

    if detected in _BULLISH:
        signal = "Bullish"
    elif detected in _BEARISH:
        signal = "Bearish"
    else:
        signal = "Neutral"

    return {"last_5": per_candle, "detected": detected, "signal": signal}
