"""Explainable 1M regime classifier: TREND, RANGE, VOLATILE_CHOP, NEWS_SHOCK, UNKNOWN.

Position size is fixed at 0.4 lot by the owner, so a regime either allows a strategy
or stands aside; there is no size scaling.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class Regime(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    VOLATILE_CHOP = "VOLATILE_CHOP"
    NEWS_SHOCK = "NEWS_SHOCK"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeParams:
    shock_bar_atr: float = 4.0     # bar range > 4x baseline ATR = shock bar
    shock_cooldown: int = 15       # stay in NEWS_SHOCK this many bars after a shock bar
    shock_atr_ratio: float = 2.5   # or ATR running 2.5x its daily baseline
    chop_atr_ratio: float = 1.5
    chop_er: float = 0.30
    trend_er: float = 0.35
    trend_slope: float = 0.30      # 15-bar change of slow EMA, in ATRs


def classify(f: pd.DataFrame, p: RegimeParams = RegimeParams()) -> pd.Series:
    shock_bar = (f["high"] - f["low"]) > p.shock_bar_atr * f["atr_base"]
    recent_shock = shock_bar.astype(float).rolling(p.shock_cooldown, min_periods=1).max() > 0
    unknown = f[["atr_ratio", "er", "slope"]].isna().any(axis=1)

    labels = np.select(
        [
            unknown,
            recent_shock | (f["atr_ratio"] > p.shock_atr_ratio),
            (f["atr_ratio"] > p.chop_atr_ratio) & (f["er"] < p.chop_er),
            (f["er"] >= p.trend_er) & (f["slope"].abs() >= p.trend_slope),
        ],
        [Regime.UNKNOWN.value, Regime.NEWS_SHOCK.value, Regime.VOLATILE_CHOP.value,
         Regime.TREND.value],
        default=Regime.RANGE.value,
    )
    return pd.Series(labels, index=f.index, name="regime")


def forward_truth(f: pd.DataFrame, horizon: int = 60, p: RegimeParams = RegimeParams()) -> pd.Series:
    """EVALUATION ONLY - uses future bars. What the next `horizon` bars actually looked like,
    using the same definitions, so classify() can be scored on whether its label holds."""
    close = f["close"]
    fut_change = (close.shift(-horizon) - close).abs()
    fut_path = close.diff().abs()[::-1].rolling(horizon).sum()[::-1].shift(-1)
    fut_er = fut_change / fut_path.replace(0, np.nan)
    rng = f["high"] - f["low"]
    fut_range_max = rng[::-1].rolling(horizon).max()[::-1].shift(-1)
    fut_range_mean = rng[::-1].rolling(horizon).mean()[::-1].shift(-1)
    fut_vol_ratio = fut_range_mean / (f["atr_base"])
    drift = (close.shift(-horizon) - close) / f["atr"]

    valid = fut_er.notna() & f["atr_base"].notna()
    labels = np.select(
        [
            ~valid,
            fut_range_max > p.shock_bar_atr * f["atr_base"],
            (fut_vol_ratio > p.chop_atr_ratio) & (fut_er < p.chop_er),
            (fut_er >= p.trend_er) & (drift.abs() >= 2.0),
        ],
        [Regime.UNKNOWN.value, Regime.NEWS_SHOCK.value, Regime.VOLATILE_CHOP.value,
         Regime.TREND.value],
        default=Regime.RANGE.value,
    )
    return pd.Series(labels, index=f.index, name="truth")


def confusion(pred: pd.Series, truth: pd.Series) -> tuple[pd.DataFrame, float]:
    mask = (pred != Regime.UNKNOWN.value) & (truth != Regime.UNKNOWN.value)
    table = pd.crosstab(pred[mask], truth[mask], rownames=["predicted"], colnames=["next 60m"])
    wrong = float((pred[mask] != truth[mask]).mean()) if mask.any() else float("nan")
    return table, wrong
