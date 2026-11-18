"""XAUUSD 1M bar store and data-quality checks for TradingView bars.

tvdatafeed returns naive timestamps in the collecting machine's local time zone
and includes the still-forming bar last; both are handled in `normalize_tv_bars`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scalper import sessions

COLUMNS = ["open", "high", "low", "close", "volume"]


def normalize_tv_bars(raw: pd.DataFrame, local_tz: str, drop_last: bool = True) -> pd.DataFrame:
    df = raw.copy()
    if "datetime" in df.columns:
        df = df.set_index("datetime")
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize(local_tz, ambiguous="NaT", nonexistent="NaT")
    df.index = idx.tz_convert("UTC")
    df.index.name = "time"
    df = df[~df.index.isna()][COLUMNS].astype(float).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if drop_last and len(df):
        df = df.iloc[:-1]
    return df


class BarStore:
    """Monthly CSV files of UTC 1M bars; merging is idempotent."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, month: pd.Period) -> Path:
        return self.root / f"{month}.csv"

    def load(self) -> pd.DataFrame:
        files = sorted(self.root.glob("*.csv"))
        if not files:
            return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], tz="UTC", name="time"))
        df = pd.concat(pd.read_csv(f, index_col="time", parse_dates=["time"]) for f in files)
        df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
        return df.sort_index()

    def merge(self, bars: pd.DataFrame) -> dict:
        """Add bars; existing timestamps are overwritten and counted as revisions."""
        self.root.mkdir(parents=True, exist_ok=True)
        added = revised = 0
        months = bars.index.tz_convert("UTC").tz_localize(None).to_period("M")
        for month, chunk in bars.groupby(months):
            path = self._path(month)
            if path.exists():
                old = pd.read_csv(path, index_col="time", parse_dates=["time"])
                old.index = pd.DatetimeIndex(old.index).tz_convert("UTC")
                common = chunk.index.intersection(old.index)
                revised += int((old.loc[common, COLUMNS] != chunk.loc[common, COLUMNS]).any(axis=1).sum())
                added += len(chunk.index.difference(old.index))
                merged = pd.concat([old[~old.index.isin(chunk.index)], chunk]).sort_index()
            else:
                added += len(chunk)
                merged = chunk
            merged.to_csv(path, index_label="time", date_format="%Y-%m-%dT%H:%M:%S%z")
        return {"added": added, "revised": revised}


@dataclass(frozen=True)
class QualityReport:
    bars: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    duplicates: int
    invalid_ohlc: int
    zero_range: int
    missing_in_session: int
    bars_by_session: dict[str, int]

    def as_text(self) -> str:
        lines = [
            f"bars: {self.bars}  range: {self.start} -> {self.end}",
            f"duplicates: {self.duplicates}  invalid OHLC: {self.invalid_ohlc}  "
            f"zero-range: {self.zero_range}",
            f"missing minutes inside open sessions: {self.missing_in_session}",
            "bars by session: " + ", ".join(f"{k}={v}" for k, v in self.bars_by_session.items()),
        ]
        return "\n".join(lines)


def quality_report(df: pd.DataFrame) -> QualityReport:
    if df.empty:
        return QualityReport(0, None, None, 0, 0, 0, 0, {})
    idx = df.index
    invalid = (
        (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
        | (df["low"] <= 0)
    )
    labels = pd.Series([sessions.session_at(t.to_pydatetime()).value for t in idx], index=idx)

    expected = pd.date_range(idx.min(), idx.max(), freq="1min", tz="UTC")
    missing = expected.difference(idx)
    missing_open = sum(
        1 for t in missing
        if sessions.session_at(t.to_pydatetime()) not in (sessions.Session.CLOSED,
                                                          sessions.Session.ROLLOVER)
    )
    return QualityReport(
        bars=len(df),
        start=idx.min(),
        end=idx.max(),
        duplicates=int(idx.duplicated().sum()),
        invalid_ohlc=int(invalid.sum()),
        zero_range=int((df["high"] == df["low"]).sum()),
        missing_in_session=missing_open,
        bars_by_session=labels.value_counts().sort_index().to_dict(),
    )
