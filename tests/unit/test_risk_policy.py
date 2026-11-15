from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from typing import Any

import pytest
from tsch_api.brokers.sim import SIM_IDENTITY, SIM_SPECS
from tsch_contracts import AccountMode, AccountType, HealthStatus, OrderProposal, Quote, Side
from tsch_risk import RiskContext, RiskPolicy, evaluate

NOW = datetime(2026, 3, 10, 9, 30, tzinfo=UTC)
QUOTE = Quote(symbol="XAUUSD", bid=D("2400.00"), ask=D("2400.20"), ts_utc=NOW)


def proposal(**kw: Any) -> OrderProposal:
    base: dict[str, Any] = dict(account_mode=AccountMode.SIM, symbol="XAUUSD", side=Side.BUY,
                                volume=D("0.01"), sl=D("2390.00"), tp=D("2420.00"),
                                strategy_id="t", strategy_version="1")
    return OrderProposal(**{**base, **kw})


def ctx(**kw: Any) -> RiskContext:
    base: dict[str, Any] = dict(
        now_utc=NOW, identity=SIM_IDENTITY, expected_identity=SIM_IDENTITY,
        health=HealthStatus(connected=True, last_heartbeat_utc=NOW), quote=QUOTE,
        spec=SIM_SPECS["XAUUSD"], equity=D("10000"), day_start_equity=D("10000"),
        peak_equity=D("10000"), open_positions=0,
    )
    return RiskContext(**{**base, **kw})


POLICY = RiskPolicy()


def blocked(p: OrderProposal, c: RiskContext, policy: RiskPolicy = POLICY) -> str:
    d = evaluate(p, c, policy)
    assert not d.allowed
    return " | ".join(d.reasons)


def test_baseline_allowed() -> None:
    d = evaluate(proposal(), ctx(), POLICY)
    assert d.allowed, d.reasons
    assert d.entry_price == D("2400.20")
    # 1020 ticks x $1 x 0.01 lot = $10.20 = 0.102% of equity
    assert d.loss_at_stop == D("10.20")
    assert len(d.snapshot_hash) == 64


def test_snapshot_is_deterministic() -> None:
    assert evaluate(proposal(), ctx(), POLICY).snapshot_hash == \
        evaluate(proposal(), ctx(), POLICY).snapshot_hash


@pytest.mark.parametrize("p,c,policy,expect", [
    (proposal(), ctx(), replace(POLICY, kill_switch=True), "kill switch"),
    (proposal(account_mode=AccountMode.LIVE_DISABLED), ctx(), POLICY, "cannot execute"),
    (proposal(account_mode=AccountMode.TRADINGVIEW_PAPER_MANUAL), ctx(), POLICY,
     "cannot execute"),
    (proposal(), ctx(identity=SIM_IDENTITY.model_copy(update={"account_type": AccountType.REAL})),
     POLICY, "not DEMO"),
    (proposal(), ctx(identity=SIM_IDENTITY.model_copy(update={"login": "X1"})), POLICY,
     "identity changed"),
    (proposal(), ctx(identity=SIM_IDENTITY.model_copy(update={"server": "Other-Live"})), POLICY,
     "identity changed"),
    (proposal(), ctx(identity=None), POLICY, "identity missing"),
    (proposal(), ctx(health=HealthStatus(connected=False, last_heartbeat_utc=NOW)), POLICY,
     "disconnected"),
    (proposal(), ctx(health=HealthStatus(connected=True,
                                         last_heartbeat_utc=NOW - timedelta(minutes=5))),
     POLICY, "heartbeat stale"),
    (proposal(), ctx(health=None), POLICY, "health unknown"),
    (proposal(), ctx(quote=None), POLICY, "no broker quote"),
    (proposal(), ctx(quote=QUOTE.model_copy(update={"ts_utc": NOW - timedelta(minutes=1)})),
     POLICY, "outside"),
    (proposal(), ctx(quote=QUOTE.model_copy(update={"ask": D("2401.00")})), POLICY, "spread"),
    (proposal(), ctx(spec=None), POLICY, "symbol spec"),
    (proposal(sl=None), ctx(), POLICY, "stop loss required"),
    (proposal(sl=D("2410.00")), ctx(), POLICY, "wrong side"),
    (proposal(side=Side.SELL, sl=D("2390.00"), tp=None), ctx(), POLICY, "wrong side"),
    (proposal(tp=D("2390.00"), sl=D("2380.00")), ctx(), POLICY, "take profit on wrong side"),
    (proposal(volume=D("0.50"), sl=D("2300.00")), ctx(), POLICY, "exceeds max"),
    (proposal(volume=D("0.015")), ctx(), POLICY, "invalid for broker"),
    (proposal(volume=D("2")), ctx(), POLICY, "exceeds policy max"),
    (proposal(symbol="BTCUSD"), ctx(), POLICY, "not whitelisted"),
    (proposal(), ctx(equity=None), POLICY, "equity unknown"),
    (proposal(), ctx(equity=D("9800"), day_start_equity=D("10000")), POLICY, "daily loss"),
    (proposal(), ctx(equity=D("9400"), day_start_equity=D("9400"), peak_equity=D("10000")),
     POLICY, "drawdown"),
    (proposal(), ctx(day_start_equity=None), POLICY, "day-start equity unknown"),
    (proposal(), ctx(open_positions=3), POLICY, "max concurrent"),
    (proposal(), ctx(open_positions=None), POLICY, "positions unknown"),
])
def test_blocks(p: OrderProposal, c: RiskContext, policy: RiskPolicy, expect: str) -> None:
    assert expect in blocked(p, c, policy)


def test_small_clock_skew_tolerated_large_future_quote_rejected() -> None:
    slightly_ahead = QUOTE.model_copy(update={"ts_utc": NOW + timedelta(milliseconds=5)})
    assert evaluate(proposal(), ctx(quote=slightly_ahead), POLICY).allowed
    far_ahead = QUOTE.model_copy(update={"ts_utc": NOW + timedelta(seconds=30)})
    assert "outside" in blocked(proposal(), ctx(quote=far_ahead))
    future_hb = HealthStatus(connected=True, last_heartbeat_utc=NOW + timedelta(minutes=5))
    assert "heartbeat stale" in blocked(proposal(), ctx(health=future_hb))


def test_internal_error_fails_closed() -> None:
    bad = ctx(equity="not-a-decimal")  # type: ignore[arg-type]
    d = evaluate(proposal(), bad, POLICY)
    assert not d.allowed
    assert any("risk engine error" in r for r in d.reasons)


@pytest.mark.parametrize("pct", [D("0"), D("2.5"), D("-1")])
def test_policy_rejects_out_of_range_cap(pct: D) -> None:
    with pytest.raises(ValueError):
        RiskPolicy(max_risk_pct=pct)
