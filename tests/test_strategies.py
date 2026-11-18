import numpy as np
import pandas as pd
import pytest

from scalper.features import build_features
from scalper.regime import classify
from scalper.strategies import (
    STRATEGIES, asian_range_breakout, generate, liquidity_sweep, open_momentum,
    vwap_reversion,
)
from tests.conftest import make_bars

NAMES = list(STRATEGIES)


@pytest.fixture(scope="module")
def feats():
    bars = make_bars(n=4000, seed=3, vol=0.9)
    f = build_features(bars)
    return bars, f, classify(f)


@pytest.mark.parametrize("name", NAMES)
def test_no_lookahead(feats, name):
    bars, f, r = feats
    full = STRATEGIES[name].fn(f)
    for cut in (1500, 2600, 3900):
        pf = build_features(bars.iloc[:cut])
        part = STRATEGIES[name].fn(pf)
        pd.testing.assert_frame_equal(part, full.iloc[:cut], check_dtype=False)


@pytest.mark.parametrize("name", NAMES)
def test_stops_and_targets_on_correct_side(feats, name):
    _, f, _ = feats
    sig = STRATEGIES[name].fn(f)
    on = sig[sig["side"] != 0]
    close = f.loc[on.index, "close"]
    assert ((close - on["stop"]) * on["side"] > 0).all()
    assert ((on["tp"] - close) * on["side"] > 0).all()


@pytest.mark.parametrize("name", NAMES)
def test_regime_gate_and_entry_rules(feats, name):
    _, f, r = feats
    sig = generate(f, r, name)
    on = sig["side"] != 0
    assert r[on].isin(STRATEGIES[name].regimes).all()
    assert f.loc[on, "entries_ok"].all()


def _flat_day(start, n, price=4000.0):
    """Very quiet bars so ATR is small and a crafted move dominates."""
    b = make_bars(start=start, n=n, vol=0.05, seed=1, price=price)
    return b


def test_asian_range_breakout_fires_once_at_london():
    # Tue 17 Nov 2026: Asia from 23:05 UTC Mon; London opens 08:00 UTC (GMT)
    b = _flat_day("2026-11-16 23:10", 600)
    t = pd.Timestamp("2026-11-17 08:30", tz="UTC")
    i = b.index.get_loc(t)
    for k, j in enumerate(range(i, i + 5)):  # push through the Asian high
        px = b["close"].iloc[i - 1] + 3.0 + k
        b.iloc[j] = [px - 0.2, px + 0.1, px - 0.3, px, 100.0]
    f = build_features(b)
    sig = asian_range_breakout(f)
    hits = sig[sig["side"] != 0]
    assert list(hits.index) == [t]
    assert hits["side"].iloc[0] == 1


def test_asian_breakout_ignored_after_cutoff():
    b = _flat_day("2026-11-16 23:10", 800)
    t = pd.Timestamp("2026-11-17 11:30", tz="UTC")
    i = b.index.get_loc(t)
    px = b["close"].iloc[i - 1] + 4.0
    b.iloc[i] = [px - 0.2, px + 0.1, px - 0.3, px, 100.0]
    sig = asian_range_breakout(build_features(b))
    assert (sig.loc[pd.Timestamp("2026-11-17 11:00", tz="UTC"):, "side"] == 0).all()


def test_open_momentum_london_continuation():
    b = _flat_day("2026-11-17 03:00", 400)
    start = b.index.get_loc(pd.Timestamp("2026-11-17 08:00", tz="UTC"))
    base = b["close"].iloc[start - 1]
    for k in range(15):
        o = base + 0.4 * k
        b.iloc[start + k] = [o, o + 0.45, o - 0.02, o + 0.4, 200.0]
    sig = open_momentum(build_features(b))
    hits = sig[sig["side"] != 0]
    assert list(hits.index) == [pd.Timestamp("2026-11-17 08:14", tz="UTC")]
    assert hits["side"].iloc[0] == 1
    assert hits["stop"].iloc[0] < base


def test_liquidity_sweep_fades_failed_break_of_prior_session_high():
    b = _flat_day("2026-11-17 03:00", 400)  # ASIA then LONDON from 08:00
    f0 = build_features(b)
    prior_hi = f0.loc[f0["session"] == "ASIA", "high"].max()
    t = pd.Timestamp("2026-11-17 09:00", tz="UTC")
    i = b.index.get_loc(t)
    c = prior_hi - 0.05
    b.iloc[i] = [c, prior_hi + 1.0, c - 0.05, c, 300.0]
    sig = liquidity_sweep(build_features(b))
    assert sig.loc[t, "side"] == -1
    assert sig.loc[t, "stop"] > prior_hi + 1.0


def test_vwap_reversion_fades_stretch():
    b = make_bars(start="2026-11-17 08:00", n=300, vol=0.3, seed=5)
    t = b.index[200]
    px = b["close"].iloc[199] - 12.0
    b.iloc[200] = [px + 0.3, px + 0.4, px - 0.1, px, 200.0]
    f = build_features(b)
    sig = vwap_reversion(f)
    assert sig.loc[t, "side"] == 1
    assert sig.loc[t, "tp"] == pytest.approx(f.loc[t, "vwap"])
