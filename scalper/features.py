"""Causal 1M features. Each row uses only that bar and earlier bars.

Bar timestamps are bar OPEN times (TradingView convention); a bar is usable once closed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scalper import sessions

ATR_N = 14
ATR_BASE_BARS = 1440       # one day of 1M bars
ATR_BASE_MIN = 240
ER_BARS = 30
EMA_FAST = 20
EMA_SLOW = 300             # ~5 hours: higher-timeframe trend proxy
SLOPE_BARS = 15


def wilder_atr(df: pd.DataFrame, n: int = ATR_N) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                    (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def efficiency_ratio(close: pd.Series, n: int = ER_BARS) -> pd.Series:
    change = (close - close.shift(n)).abs()
    path = close.diff().abs().rolling(n).sum()
    return (change / path.replace(0, np.nan)).fillna(0.0).where(path.notna())


def build_features(bars: pd.DataFrame) -> pd.DataFrame:
    f = bars[["open", "high", "low", "close", "volume"]].copy()
    f["atr"] = wilder_atr(f)
    f["atr_base"] = f["atr"].rolling(ATR_BASE_BARS, min_periods=ATR_BASE_MIN).median()
    f["atr_ratio"] = f["atr"] / f["atr_base"]
    f["er"] = efficiency_ratio(f["close"])
    f["ema_fast"] = f["close"].ewm(span=EMA_FAST, adjust=False).mean()
    f["ema_slow"] = f["close"].ewm(span=EMA_SLOW, adjust=False, min_periods=EMA_SLOW).mean()
    f["slope"] = (f["ema_slow"] - f["ema_slow"].shift(SLOPE_BARS)) / f["atr"]

    close_times = [t.to_pydatetime() + pd.Timedelta(minutes=1) for t in f.index]
    f["session"] = [sessions.session_at(t.to_pydatetime()).value for t in f.index]
    f["entries_ok"] = [sessions.entries_allowed(t) for t in close_times]
    f["tday"] = [sessions.trading_day(t.to_pydatetime()) for t in f.index]
    f["session_id"] = (f["session"] != f["session"].shift()).cumsum()

    typical = (f["high"] + f["low"] + f["close"]) / 3
    vol = f["volume"].clip(lower=1.0)
    grp = f["session_id"]
    f["vwap"] = (typical * vol).groupby(grp).cumsum() / vol.groupby(grp).cumsum()
    f["bars_in_session"] = f.groupby(grp).cumcount()
    return f
