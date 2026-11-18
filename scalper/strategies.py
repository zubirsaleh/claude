"""Candidate XAUUSD 1M strategies. Signals only - execution and risk live elsewhere.

A signal on bar t is known when bar t closes; entry reference is that close.
Output frame per strategy: side (+1 buy, -1 sell, 0 none), stop, tp.
None of these is validated. They are hypotheses for walk-forward testing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Callable

import numpy as np
import pandas as pd

from scalper.regime import Regime
from scalper.sessions import LONDON, NEW_YORK

RR = 1.5  # reward:risk for fixed-target strategies


@dataclass(frozen=True)
class StrategySpec:
    name: str
    fn: Callable[[pd.DataFrame], pd.DataFrame]
    regimes: frozenset[str]
    edge: str
    counterparty: str


def _empty(f: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"side": 0, "stop": np.nan, "tp": np.nan}, index=f.index)


def _cooldown(side: np.ndarray, bars: int) -> np.ndarray:
    out = np.zeros_like(side)
    last = -10**9
    for i, s in enumerate(side):
        if s != 0 and i - last > bars:
            out[i] = s
            last = i
    return out


def _fill(f: pd.DataFrame, side: np.ndarray, stop: pd.Series, tp: pd.Series) -> pd.DataFrame:
    out = _empty(f)
    on = side != 0
    out.loc[on, "side"] = side[on]
    out.loc[on, "stop"] = stop[on]
    out.loc[on, "tp"] = tp[on]
    return out


def _allowed(f: pd.DataFrame, allowed: pd.Series | None) -> pd.Series:
    return pd.Series(True, index=f.index) if allowed is None else allowed.astype(bool)


def _local_time(index: pd.DatetimeIndex, tz) -> pd.Series:
    return pd.Series([t.time() for t in index.tz_convert(tz)], index=index)


def asian_range_breakout(f: pd.DataFrame, allowed: pd.Series | None = None, buffer_atr: float = 0.1,
                         stop_atr: float = 2.0, last_entry: time = time(11, 0)) -> pd.DataFrame:
    """First close beyond the Asian-session range during London's first hours."""
    asia = f["session"] == "ASIA"
    hi = f["high"].where(asia).groupby(f["tday"]).cummax().groupby(f["tday"]).ffill()
    lo = f["low"].where(asia).groupby(f["tday"]).cummin().groupby(f["tday"]).ffill()
    ldn = _local_time(f.index, LONDON)
    window = f["session"].isin(["LONDON", "OVERLAP"]) & (ldn < last_entry) & _allowed(f, allowed)
    buf = buffer_atr * f["atr"]
    up = window & (f["close"] > hi + buf) & (f["close"].shift() <= hi + buf)
    dn = window & (f["close"] < lo - buf) & (f["close"].shift() >= lo - buf)
    side = np.where(up, 1, np.where(dn, -1, 0))
    # one signal per trading day per direction
    first = pd.Series(side, index=f.index).groupby([f["tday"], side]).cumcount() == 0
    side = np.where(first, side, 0)
    dist = stop_atr * f["atr"]
    stop = f["close"] - side * dist
    tp = f["close"] + side * RR * dist
    return _fill(f, side, stop, tp)


def open_momentum(f: pd.DataFrame, allowed: pd.Series | None = None, window: int = 15, move_atr: float = 1.5,
                  min_er: float = 0.4) -> pd.DataFrame:
    """Continuation after a strong, efficient first 15 minutes of London (08:00) or NY (09:30)."""
    ok = _allowed(f, allowed).to_numpy()
    side = np.zeros(len(f), dtype=int)
    stop = pd.Series(np.nan, index=f.index)
    for tz, open_t in ((LONDON, time(8, 0)), (NEW_YORK, time(9, 30))):
        local = f.index.tz_convert(tz)
        mins = (local.hour * 60 + local.minute) - (open_t.hour * 60 + open_t.minute)
        last_bar = np.where(mins == window - 1)[0]
        for i in last_bar:
            if not ok[i]:
                continue
            j = i - (window - 1)
            if j < 0 or (local[i] - local[j]).total_seconds() != (window - 1) * 60:
                continue  # gap inside the opening window
            seg = f.iloc[j:i + 1]
            move = seg["close"].iloc[-1] - seg["open"].iloc[0]
            path = (seg["close"].diff().abs().sum()
                    + abs(seg["close"].iloc[0] - seg["open"].iloc[0]))
            atr = f["atr"].iloc[j]
            if np.isnan(atr) or path == 0:
                continue
            if abs(move) >= move_atr * atr and abs(move) / path >= min_er:
                s = 1 if move > 0 else -1
                side[i] = s
                stop.iloc[i] = (seg["low"].min() - 0.2 * atr) if s > 0 else (seg["high"].max() + 0.2 * atr)
    risk = (f["close"] - stop).abs()
    tp = f["close"] + pd.Series(side, index=f.index) * RR * risk
    return _fill(f, side, stop, tp)


def vwap_reversion(f: pd.DataFrame, allowed: pd.Series | None = None, dev_sd: float = 2.0, stop_atr: float = 1.5,
                   min_session_bars: int = 30, cooldown: int = 15) -> pd.DataFrame:
    """Fade stretched moves back to the session VWAP."""
    dev = f["close"] - f["vwap"]
    sd = dev.rolling(120, min_periods=60).std()
    ok = (f["bars_in_session"] >= min_session_bars) & _allowed(f, allowed)
    dist = stop_atr * f["atr"]
    room = dev.abs() >= dist  # target at least as far as the stop
    side = np.where(ok & room & (dev > dev_sd * sd), -1,
                    np.where(ok & room & (dev < -dev_sd * sd), 1, 0))
    side = _cooldown(side, cooldown)
    stop = f["close"] - side * dist
    return _fill(f, side, stop, f["vwap"])


def liquidity_sweep(f: pd.DataFrame, allowed: pd.Series | None = None, poke_atr: float = 0.1, stop_atr: float = 0.3,
                    cooldown: int = 30) -> pd.DataFrame:
    """Bar runs the prior session's high/low and closes back inside: stops were taken, fade."""
    g = f.groupby("session_id")
    prev_hi = f["session_id"].map(g["high"].max().shift())
    prev_lo = f["session_id"].map(g["low"].min().shift())
    poke = poke_atr * f["atr"]
    ok = _allowed(f, allowed)
    sell = ok & (f["high"] > prev_hi + poke) & (f["close"] < prev_hi)
    buy = ok & (f["low"] < prev_lo - poke) & (f["close"] > prev_lo)
    side = _cooldown(np.where(sell, -1, np.where(buy, 1, 0)), cooldown)
    stop = np.where(side < 0, f["high"] + stop_atr * f["atr"], f["low"] - stop_atr * f["atr"])
    stop = pd.Series(stop, index=f.index)
    tp = f["close"] + pd.Series(side, index=f.index) * RR * (f["close"] - stop).abs()
    return _fill(f, side, stop, tp)


def ema_pullback(f: pd.DataFrame, allowed: pd.Series | None = None, stop_atr: float = 0.5, cooldown: int = 15) -> pd.DataFrame:
    """In an established trend, buy a dip to the fast EMA that closes back with the trend."""
    up = (f["slope"] > 0) & (f["low"] <= f["ema_fast"]) & (f["close"] > f["ema_fast"]) \
        & (f["close"] > f["open"]) & (f["close"] > f["ema_slow"])
    dn = (f["slope"] < 0) & (f["high"] >= f["ema_fast"]) & (f["close"] < f["ema_fast"]) \
        & (f["close"] < f["open"]) & (f["close"] < f["ema_slow"])
    ok = _allowed(f, allowed)
    side = _cooldown(np.where(up & ok, 1, np.where(dn & ok, -1, 0)), cooldown)
    stop = np.where(side > 0, f["low"] - stop_atr * f["atr"], f["high"] + stop_atr * f["atr"])
    stop = pd.Series(stop, index=f.index)
    tp = f["close"] + pd.Series(side, index=f.index) * RR * (f["close"] - stop).abs()
    return _fill(f, side, stop, tp)


STRATEGIES: dict[str, StrategySpec] = {s.name: s for s in [
    StrategySpec(
        "asian_range_breakout", asian_range_breakout,
        frozenset({Regime.TREND.value, Regime.RANGE.value}),
        "London's arrival of liquidity resolves the quiet Asian range directionally.",
        "Asian-session range sellers and stops resting just beyond the range."),
    StrategySpec(
        "open_momentum", open_momentum,
        frozenset({Regime.TREND.value}),
        "Strong, efficient opening flow at London/NY open tends to continue for minutes.",
        "Early faders and late participants still rebalancing into the open."),
    StrategySpec(
        "vwap_reversion", vwap_reversion,
        frozenset({Regime.RANGE.value}),
        "In a balanced session, large deviations from VWAP mean-revert as liquidity providers absorb them.",
        "Impatient momentum chasers paying up away from fair value."),
    StrategySpec(
        "liquidity_sweep", liquidity_sweep,
        frozenset({Regime.RANGE.value, Regime.TREND.value}),
        "Runs on obvious prior-session highs/lows trigger stops; failure to hold signals exhaustion.",
        "Breakout traders and stop-loss orders clustered at the prior session extreme."),
    StrategySpec(
        "ema_pullback", ema_pullback,
        frozenset({Regime.TREND.value}),
        "Trends on gold persist intraday; shallow pullbacks offer better entry than chasing.",
        "Counter-trend scalpers fading the move at the fast average."),
]}


def generate(f: pd.DataFrame, regimes: pd.Series, name: str) -> pd.DataFrame:
    """Strategy signals gated by regime and session entry rules."""
    spec = STRATEGIES[name]
    allowed = regimes.isin(spec.regimes) & f["entries_ok"] & f["atr"].notna()
    return spec.fn(f, allowed)
