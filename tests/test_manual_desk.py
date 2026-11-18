from datetime import datetime, timedelta, timezone

import pytest

from scalper.journal import Journal
from scalper.manual_desk import DeskError, ManualDesk, format_alert, format_status
from scalper.risk import OrderRequest, RiskEngine
from scalper.settings import LIMITS

NOW = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)  # Tuesday, NY session
BAR = NOW - timedelta(seconds=30)


@pytest.fixture
def desk(tmp_path):
    risk = RiskEngine(tmp_path / "risk.json")
    return ManualDesk(tmp_path / "desk.json", risk, Journal(tmp_path / "j.jsonl"))


def buy(stop=3995.0, tp=4008.0):
    return OrderRequest("BUY", LIMITS.units, stop, tp)


def test_alert_then_taken_then_stopped(desk):
    d, t = desk.propose(buy(), 4000.0, BAR, NOW)
    assert d.allowed and t.status == "ALERTED"
    assert t.entry == pytest.approx(4000.35)
    assert "#1" in format_alert(t, LIMITS.lot_size)
    desk.taken(1, NOW + timedelta(seconds=20), fill=4000.50)
    hits = desk.on_bar(high=4001.0, low=3994.0, close=3996.0, now=NOW + timedelta(minutes=1))
    assert hits[0].close_reason.startswith("stop")
    assert hits[0].pnl == pytest.approx((3995.0 - 4000.50) * 40)
    assert desk.equity() == pytest.approx(LIMITS.account_size_usd - 220.0)
    assert desk.risk.state.consecutive_losses == 1


def test_stop_assumed_when_bar_touches_both(desk):
    desk.propose(buy(), 4000.0, BAR, NOW)
    desk.taken(1, NOW)
    hits = desk.on_bar(high=4009.0, low=3994.0, close=4000.0, now=NOW + timedelta(minutes=1))
    assert hits[0].close_reason.startswith("stop")


def test_target_hit_for_sell(desk):
    d, t = desk.propose(OrderRequest("SELL", 40, 4005.0, 3992.0), 4000.0, BAR, NOW)
    assert d.allowed
    desk.taken(t.id, NOW)
    hits = desk.on_bar(high=4001.0, low=3991.0, close=3993.0, now=NOW + timedelta(minutes=1))
    assert hits[0].close_reason.startswith("target")
    assert hits[0].pnl == pytest.approx((4000.0 - 3992.0) * 40)


def test_alert_expires_and_cannot_be_taken(desk):
    desk.propose(buy(), 4000.0, BAR, NOW)
    with pytest.raises(DeskError):
        desk.taken(1, NOW + timedelta(minutes=3))
    assert desk.trades[1].status == "EXPIRED"


def test_one_active_trade_at_a_time(desk):
    desk.propose(buy(), 4000.0, BAR, NOW)
    d, t = desk.propose(buy(), 4000.0, BAR, NOW)
    assert not d.allowed and t is None
    desk.skip(1)
    assert desk.propose(buy(), 4000.0, BAR, NOW)[0].allowed


def test_stop_beyond_400_rejected(desk):
    d, _ = desk.propose(OrderRequest("BUY", 40, 3990.10, None), 4000.0, BAR, NOW)
    assert not d.allowed and any("trade risk 410" in r for r in d.reasons)


def test_stale_bar_rejected(desk):
    d, _ = desk.propose(buy(), 4000.0, NOW - timedelta(minutes=3), NOW)
    assert not d.allowed and any("stale" in r for r in d.reasons)


def test_fill_beyond_stop_rejected(desk):
    desk.propose(buy(), 4000.0, BAR, NOW)
    with pytest.raises(DeskError):
        desk.taken(1, NOW, fill=3994.0)


def test_daily_stop_after_three_full_losses(desk):
    t0 = NOW
    for i in range(3):
        # entry 4000.35 (incl. assumed spread), stop 3990.40 -> 398 risk each
        _, t = desk.propose(OrderRequest("BUY", 40, 3990.40, None), 4000.0,
                            t0 - timedelta(seconds=30), t0)
        assert t is not None, f"trade {i} blocked"
        desk.taken(t.id, t0)
        desk.close(t.id, 3990.40, t0)
        t0 += timedelta(minutes=5)
    d, _ = desk.propose(buy(), 4000.0, t0 - timedelta(seconds=30), t0)
    assert not d.allowed
    assert any("daily" in r for r in d.reasons)


def test_kill_switch_blocks_and_lists_open_trades(desk):
    desk.propose(buy(), 4000.0, BAR, NOW)
    desk.taken(1, NOW)
    still_open = desk.kill("owner /kill")
    assert [t.id for t in still_open] == [1]
    assert not desk.propose(buy(), 4000.0, BAR, NOW)[0].allowed
    assert "Kill switch: ON" in format_status(desk)


def test_state_survives_restart(tmp_path):
    risk = RiskEngine(tmp_path / "risk.json")
    desk = ManualDesk(tmp_path / "desk.json", risk, Journal(tmp_path / "j.jsonl"))
    desk.propose(buy(), 4000.0, BAR, NOW)
    desk.taken(1, NOW)
    desk.close(1, 4004.0, NOW)
    again = ManualDesk(tmp_path / "desk.json", RiskEngine(tmp_path / "risk.json"),
                       Journal(tmp_path / "j.jsonl"))
    assert again.trades[1].status == "CLOSED"
    assert again.realized == pytest.approx(desk.realized)
