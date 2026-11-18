from datetime import date, datetime, timedelta, timezone

import pytest

from scalper.sessions import (
    Session, entries_allowed, in_news_blackout, session_at, trading_day,
)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.mark.parametrize("ts,expected", [
    (utc(2026, 11, 17, 3, 0), Session.ASIA),
    (utc(2026, 11, 17, 9, 0), Session.LONDON),
    (utc(2026, 11, 17, 14, 0), Session.OVERLAP),      # 09:00 NY / 14:00 London
    (utc(2026, 11, 17, 18, 0), Session.NEW_YORK),
    (utc(2026, 11, 17, 22, 0), Session.ROLLOVER),     # 17:00 NY
    (utc(2026, 11, 17, 23, 10), Session.ASIA),        # 18:10 NY, after daily break
    (utc(2026, 11, 21, 12, 0), Session.CLOSED),       # Saturday
    (utc(2026, 11, 22, 22, 0), Session.CLOSED),       # Sunday 17:00 NY, before reopen
    (utc(2026, 11, 22, 23, 10), Session.ASIA),        # Sunday reopen
])
def test_session_labels(ts, expected):
    assert session_at(ts) == expected


def test_dst_shifts_overlap():
    assert session_at(utc(2026, 1, 13, 12, 30)) == Session.LONDON    # 07:30 NY EST
    assert session_at(utc(2026, 7, 14, 12, 30)) == Session.OVERLAP   # 08:30 NY EDT
    # US on DST, UK not yet (10 March 2026): 08:30 NY, 12:30 London
    assert session_at(utc(2026, 3, 10, 12, 30)) == Session.OVERLAP


def test_friday_entry_cutoff():
    assert entries_allowed(utc(2026, 11, 20, 20, 59))     # 15:59 NY
    assert not entries_allowed(utc(2026, 11, 20, 21, 0))  # 16:00 NY
    assert not entries_allowed(utc(2026, 11, 17, 22, 0))  # rollover


def test_trading_day_rolls_at_ny_5pm():
    assert trading_day(utc(2026, 11, 17, 21, 59)) == date(2026, 11, 17)
    assert trading_day(utc(2026, 11, 17, 22, 0)) == date(2026, 11, 18)


def test_news_blackout():
    nfp = utc(2026, 12, 4, 13, 30)
    assert in_news_blackout(nfp - timedelta(minutes=10), [nfp], 15)
    assert in_news_blackout(nfp + timedelta(minutes=15), [nfp], 15)
    assert not in_news_blackout(nfp + timedelta(minutes=16), [nfp], 15)


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        session_at(datetime(2026, 11, 17, 12, 0))
