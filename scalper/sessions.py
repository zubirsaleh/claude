"""Trading-session clock for XAUUSD, DST-aware.

All inputs are timezone-aware datetimes; labels are derived from local
exchange-city time so DST shifts in London and New York are handled.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")

ROLLOVER_START = time(16, 55)
ROLLOVER_END = time(18, 5)
FRIDAY_LAST_ENTRY = time(16, 0)


class Session(str, Enum):
    ASIA = "ASIA"
    LONDON = "LONDON"
    OVERLAP = "OVERLAP"
    NEW_YORK = "NEW_YORK"
    ROLLOVER = "ROLLOVER"
    CLOSED = "CLOSED"


def _require_aware(ts: datetime) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")


def session_at(ts: datetime) -> Session:
    _require_aware(ts)
    ny = ts.astimezone(NEW_YORK)
    ldn = ts.astimezone(LONDON)
    t, wd = ny.time(), ny.weekday()

    if wd == 5 or (wd == 4 and t >= ROLLOVER_START) or (wd == 6 and t < ROLLOVER_END):
        return Session.CLOSED
    if ROLLOVER_START <= t < ROLLOVER_END:
        return Session.ROLLOVER

    in_london = time(8, 0) <= ldn.time() < time(17, 0)
    in_ny = time(8, 0) <= t < ROLLOVER_START
    if in_london and in_ny:
        return Session.OVERLAP
    if in_london:
        return Session.LONDON
    if in_ny:
        return Session.NEW_YORK
    return Session.ASIA


def entries_allowed(ts: datetime) -> bool:
    if session_at(ts) in (Session.ROLLOVER, Session.CLOSED):
        return False
    ny = ts.astimezone(NEW_YORK)
    return not (ny.weekday() == 4 and ny.time() >= FRIDAY_LAST_ENTRY)


def trading_day(ts: datetime) -> date:
    """The trading day rolls over at 17:00 New York time."""
    _require_aware(ts)
    return (ts.astimezone(NEW_YORK) + timedelta(hours=7)).date()


def in_news_blackout(ts: datetime, events: list[datetime], minutes: int) -> bool:
    _require_aware(ts)
    window = timedelta(minutes=minutes)
    return any(abs(ts - ev) <= window for ev in events)
