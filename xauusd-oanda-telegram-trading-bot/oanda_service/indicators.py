"""Technical indicator engine for XAU/USD.

Indicators are computed with pandas/numpy directly so the service has no
heavy/fragile native dependencies. Every value is derived from the supplied
candles only — nothing is fabricated. Callers must pass *completed* candles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = _ema(close, fast) - _ema(close, slow)
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def _stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, smooth: int = 3):
    low_min = df["low"].rolling(k).min()
    high_max = df["high"].rolling(k).max()
    raw_k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    k_line = raw_k.rolling(smooth).mean()
    d_line = k_line.rolling(d).mean()
    return k_line, d_line


def _swings(df: pd.DataFrame, left: int = 2, right: int = 2):
    """Return indices of swing highs and lows using a simple fractal rule."""
    highs, lows = [], []
    h, l = df["high"].values, df["low"].values
    n = len(df)
    for i in range(left, n - right):
        window_h = h[i - left : i + right + 1]
        window_l = l[i - left : i + right + 1]
        if h[i] == window_h.max() and (window_h.argmax() == left):
            highs.append(i)
        if l[i] == window_l.min() and (window_l.argmin() == left):
            lows.append(i)
    return highs, lows


def _round(value, digits: int = 3):
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return None
    return round(float(value), digits)


def support_resistance(df: pd.DataFrame, lookback: int = 20) -> dict:
    """Recent support/resistance from the last ``lookback`` candles."""
    window = df.tail(lookback)
    if window.empty:
        return {"support": None, "resistance": None}
    return {
        "support": _round(window["low"].min()),
        "resistance": _round(window["high"].max()),
    }


def market_structure(df: pd.DataFrame) -> str:
    """Classify trend structure from the last few swing highs/lows."""
    highs, lows = _swings(df)
    if len(highs) < 2 or len(lows) < 2:
        return "Insufficient swing data"

    last_highs = [df["high"].iloc[i] for i in highs[-2:]]
    last_lows = [df["low"].iloc[i] for i in lows[-2:]]

    higher_high = last_highs[-1] > last_highs[-2]
    higher_low = last_lows[-1] > last_lows[-2]
    lower_high = last_highs[-1] < last_highs[-2]
    lower_low = last_lows[-1] < last_lows[-2]

    if higher_high and higher_low:
        return "Uptrend (higher highs, higher lows)"
    if lower_high and lower_low:
        return "Downtrend (lower highs, lower lows)"
    return "Range / consolidation"


def recent_trend(df: pd.DataFrame, length: int = 10) -> str:
    """Short-term trend based on the slope of the closing prices."""
    closes = df["close"].tail(length)
    if len(closes) < 2:
        return "Unknown"
    change = closes.iloc[-1] - closes.iloc[0]
    pct = change / closes.iloc[0] * 100 if closes.iloc[0] else 0
    if pct > 0.15:
        return "Rising"
    if pct < -0.15:
        return "Falling"
    return "Sideways"


def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute the full indicator set and return a flat, JSON-safe dict."""
    if df.empty or len(df) < 30:
        raise ValueError("Not enough candles to compute indicators (need >= 30).")

    close = df["close"].astype(float)

    rsi = _rsi(close)
    macd_line, macd_signal, macd_hist = _macd(close)
    atr = _atr(df)
    stoch_k, stoch_d = _stochastic(df)

    ema9 = _ema(close, 9)
    ema21 = _ema(close, 21)
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    bb_upper = mid + 2 * std
    bb_lower = mid - 2 * std

    sr = support_resistance(df)

    return {
        "price": _round(close.iloc[-1]),
        "rsi_14": _round(rsi.iloc[-1], 2),
        "macd": _round(macd_line.iloc[-1], 4),
        "macd_signal": _round(macd_signal.iloc[-1], 4),
        "macd_hist": _round(macd_hist.iloc[-1], 4),
        "macd_hist_prev": _round(macd_hist.iloc[-2], 4) if len(macd_hist) > 1 else None,
        "bb_upper": _round(bb_upper.iloc[-1]),
        "bb_mid": _round(mid.iloc[-1]),
        "bb_lower": _round(bb_lower.iloc[-1]),
        "ema_9": _round(ema9.iloc[-1]),
        "ema_21": _round(ema21.iloc[-1]),
        "ema_50": _round(ema50.iloc[-1]),
        "ema_200": _round(ema200.iloc[-1]),
        "atr_14": _round(atr.iloc[-1]),
        "atr_pct": _round(atr.iloc[-1] / close.iloc[-1] * 100, 3) if close.iloc[-1] else None,
        "stoch_k": _round(stoch_k.iloc[-1], 2),
        "stoch_d": _round(stoch_d.iloc[-1], 2),
        "support": sr["support"],
        "resistance": sr["resistance"],
        "market_structure": market_structure(df),
        "recent_trend": recent_trend(df),
    }
