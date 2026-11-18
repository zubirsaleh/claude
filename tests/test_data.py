import pandas as pd

from scalper.data import BarStore, normalize_tv_bars, quality_report


def raw_bars(start="2026-11-17 09:00", n=5, tz=None, price=4000.0):
    idx = pd.date_range(start, periods=n, freq="1min", tz=tz)
    return pd.DataFrame({
        "datetime": idx.tz_localize(None) if tz else idx,
        "symbol": "OANDA:XAUUSD",
        "open": price, "high": price + 1, "low": price - 1, "close": price + 0.5,
        "volume": 100.0,
    })


def test_normalize_converts_local_to_utc_and_drops_forming_bar():
    df = normalize_tv_bars(raw_bars("2026-11-17 17:00", n=3), "Asia/Kuala_Lumpur")
    assert str(df.index.tz) == "UTC"
    assert df.index[0] == pd.Timestamp("2026-11-17 09:00", tz="UTC")
    assert len(df) == 2
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_normalize_drops_ambiguous_dst_times():
    # 01:00-01:59 on 1 Nov 2026 occurs twice in New York
    raw = raw_bars("2026-11-01 00:58", n=4)
    df = normalize_tv_bars(raw, "America/New_York", drop_last=False)
    assert len(df) == 2


def test_store_merge_is_idempotent_and_counts_revisions(tmp_path):
    store = BarStore(tmp_path)
    bars = normalize_tv_bars(raw_bars(n=6), "UTC")
    assert store.merge(bars) == {"added": 5, "revised": 0}
    assert store.merge(bars) == {"added": 0, "revised": 0}
    changed = bars.copy()
    changed.iloc[-1, changed.columns.get_loc("close")] += 1
    assert store.merge(changed) == {"added": 0, "revised": 1}
    loaded = store.load()
    assert len(loaded) == 5
    assert loaded["close"].iloc[-1] == bars["close"].iloc[-1] + 1
    assert str(loaded.index.tz) == "UTC"


def test_store_splits_by_month(tmp_path):
    store = BarStore(tmp_path)
    store.merge(normalize_tv_bars(raw_bars("2026-10-30 20:58", n=4), "UTC"))
    assert sorted(p.name for p in tmp_path.glob("*.csv")) == ["2026-10.csv"]
    store.merge(normalize_tv_bars(raw_bars("2026-11-02 09:00", n=3), "UTC"))
    assert len(list(tmp_path.glob("*.csv"))) == 2
    assert len(store.load()) == 5


def test_quality_report_flags_gaps_and_bad_bars():
    df = normalize_tv_bars(raw_bars(n=11), "UTC")
    df = df.drop(df.index[3])  # one missing minute in LONDON
    df.iloc[0, df.columns.get_loc("high")] = 3990.0  # high below open
    rep = quality_report(df)
    assert rep.bars == 9
    assert rep.missing_in_session == 1
    assert rep.invalid_ohlc == 1
    assert rep.bars_by_session == {"LONDON": 9}


def test_quality_report_ignores_weekend_gap():
    fri = normalize_tv_bars(raw_bars("2026-11-20 21:51", n=4), "UTC", drop_last=False)
    sun = normalize_tv_bars(raw_bars("2026-11-22 23:05", n=3), "UTC", drop_last=False)
    rep = quality_report(pd.concat([fri, sun]))
    assert rep.missing_in_session == 0
