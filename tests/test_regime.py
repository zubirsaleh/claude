import numpy as np
import pandas as pd
import pytest

from scalper.features import build_features
from scalper.regime import Regime, classify, confusion, forward_truth
from tests.conftest import make_bars


def test_features_and_regime_have_no_lookahead(bars):
    full_f = build_features(bars)
    full_r = classify(full_f)
    for cut in (400, 1200, 2500):
        part_f = build_features(bars.iloc[:cut])
        cols = ["atr", "atr_base", "er", "ema_fast", "ema_slow", "slope", "vwap", "session_id"]
        pd.testing.assert_frame_equal(part_f[cols], full_f[cols].iloc[:cut])
        pd.testing.assert_series_equal(classify(part_f), full_r.iloc[:cut])


def test_warmup_is_unknown(bars):
    r = classify(build_features(bars))
    assert (r.iloc[:239] == Regime.UNKNOWN.value).all()


def test_steady_trend_labelled_trend():
    bars = make_bars(n=1500, vol=0.3, drift=0.25)
    r = classify(build_features(bars)).iloc[600:]
    assert (r == Regime.TREND.value).mean() > 0.6


def test_driftless_noise_mostly_range():
    bars = make_bars(n=1500, vol=0.5, drift=0.0)
    r = classify(build_features(bars)).iloc[600:]
    assert (r == Regime.RANGE.value).mean() > 0.6


def test_spike_triggers_news_shock_then_decays():
    bars = make_bars(n=1500, vol=0.5)
    i = 1000
    bars.iloc[i, bars.columns.get_loc("high")] = bars["close"].iloc[i] + 15.0
    r = classify(build_features(bars))
    assert (r.iloc[i:i + 15] == Regime.NEWS_SHOCK.value).all()
    assert r.iloc[i + 60] != Regime.NEWS_SHOCK.value


def test_forward_truth_and_confusion_shapes(bars):
    f = build_features(bars)
    truth = forward_truth(f)
    assert (truth.iloc[-60:] == Regime.UNKNOWN.value).all()
    table, wrong = confusion(classify(f), truth)
    assert 0.0 <= wrong <= 1.0
    assert table.values.sum() > 0
