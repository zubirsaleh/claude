from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from tsch_api.brokers.sim import SIM_IDENTITY, SimBroker
from tsch_contracts import (
    AccountMode,
    ApprovedOrder,
    BrokerTimeout,
    DataSource,
    OrderProposal,
    ReceiptStatus,
    Side,
    Timeframe,
)

T0 = datetime(2026, 3, 10, 9, 30, tzinfo=UTC)


def order(sim: SimBroker, now: datetime, **kw: object) -> ApprovedOrder:
    p = OrderProposal(account_mode=AccountMode.SIM, symbol="XAUUSD", side=Side.BUY,
                      volume=D("0.10"), sl=D("2000"), tp=None, strategy_id="t",
                      strategy_version="1")
    base = dict(proposal=p, idempotency_key=secrets.token_urlsafe(24), identity=SIM_IDENTITY,
                approved_by="op", approved_utc=now, expires_utc=now + timedelta(seconds=60),
                risk_snapshot_hash="x" * 64)
    base.update(kw)
    return ApprovedOrder(**base)  # type: ignore[arg-type]


def test_quotes_and_candles_are_deterministic() -> None:
    a, b = SimBroker(clock=lambda: T0), SimBroker(clock=lambda: T0)
    assert a.get_quote("XAUUSD") == b.get_quote("XAUUSD")
    ca = a.get_candles("EURUSD", Timeframe.M15, T0 - timedelta(hours=6), T0)
    assert ca == b.get_candles("EURUSD", Timeframe.M15, T0 - timedelta(hours=6), T0)
    assert len(ca) == 24
    for bar in ca:
        assert bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
        assert bar.source == DataSource.SIMULATED


def test_spread_matches_spec() -> None:
    q = SimBroker(clock=lambda: T0).get_quote("XAUUSD")
    assert q.ask - q.bid == D("0.20")


def test_submit_is_idempotent() -> None:
    sim = SimBroker(clock=lambda: T0)
    o = order(sim, T0)
    r1 = sim.submit_approved_demo_order(o)
    r2 = sim.submit_approved_demo_order(o)
    assert r1 == r2 and r1.status == ReceiptStatus.ACKED
    fills, _ = sim.get_fills()
    assert len(fills) == 1 and len(sim.get_positions()) == 1


def test_expired_and_wrong_identity_rejected() -> None:
    sim = SimBroker(clock=lambda: T0)
    r = sim.submit_approved_demo_order(order(sim, T0, expires_utc=T0 - timedelta(seconds=1)))
    assert r.status == ReceiptStatus.REJECTED and "expired" in r.message
    other = SIM_IDENTITY.model_copy(update={"login": "SIM000002"})
    r = sim.submit_approved_demo_order(order(sim, T0, identity=other))
    assert r.status == ReceiptStatus.REJECTED and "identity" in r.message
    assert sim.get_fills()[0] == []


def test_timeout_after_fill_is_discoverable() -> None:
    sim = SimBroker(clock=lambda: T0)
    o = order(sim, T0)
    sim.inject_next_submit = "timeout_filled"
    with pytest.raises(BrokerTimeout):
        sim.submit_approved_demo_order(o)
    found = sim.find_by_client_id(o.idempotency_key)
    assert found is not None and found.status == ReceiptStatus.ACKED
    # A retry with the same key must not create a second fill.
    sim.submit_approved_demo_order(o)
    assert len(sim.get_fills()[0]) == 1


def test_close_books_realised_pnl_and_costs() -> None:
    now = [T0]
    sim = SimBroker(clock=lambda: now[0])
    r = sim.submit_approved_demo_order(order(sim, T0))
    now[0] = T0 + timedelta(minutes=30)
    exit_bid = sim.get_quote("XAUUSD").bid
    c = sim.close_demo_position(r.position_id or "", secrets.token_urlsafe(24))
    assert c.status == ReceiptStatus.ACKED
    fills, _ = sim.get_fills()
    assert [f.entry for f in fills] == ["IN", "OUT"]
    out = fills[1]
    expected = ((exit_bid - (r.fill_price or D(0))) / D("0.01") * D("1") * D("0.10")).quantize(
        D("0.01"))
    assert out.profit == expected
    st = sim.get_account_state()
    assert st.balance == D("10000.00") + expected + 2 * D("-3.50") * D("0.10")
    assert sim.get_positions() == []
