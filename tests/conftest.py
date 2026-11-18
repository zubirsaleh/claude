import numpy as np
import pandas as pd
import pytest


def make_bars(start="2026-11-16 23:10", n=3000, seed=7, vol=0.8, drift=0.0, price=4000.0):
    """Synthetic 1M bars (UTC bar-open times), random walk with tick volume."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    steps = rng.normal(drift, vol, n)
    close = price + np.cumsum(steps)
    open_ = np.concatenate([[price], close[:-1]])
    wick = np.abs(rng.normal(0, vol * 0.6, (2, n)))
    high = np.maximum(open_, close) + wick[0]
    low = np.minimum(open_, close) - wick[1]
    vol_ = rng.integers(50, 400, n).astype(float)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": vol_}, index=pd.DatetimeIndex(idx, name="time"))


@pytest.fixture
def bars():
    return make_bars()
