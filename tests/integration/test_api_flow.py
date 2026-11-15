from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ..conftest import Harness

BUY = {"account_mode": "SIM", "symbol": "XAUUSD", "side": "BUY", "volume": "0.01",
       "sl": "2000.00", "strategy_id": "manual", "strategy_version": "0.0.0",
       "reason": "integration test"}


def _sl_below(h: Harness) -> str:
    bid = h.sim.get_quote("XAUUSD").bid
    return str(bid - 10)


def propose(h: Harness, **kw: Any) -> dict[str, Any]:
    body = {**BUY, "sl": _sl_below(h), **kw}
    r = h.client.post("/api/v1/orders/proposals", json=body, headers=h.auth)
    assert r.status_code == 201, r.text
    return dict(r.json())


def act(h: Harness, cid: str, action: str, expect: int = 200) -> dict[str, Any]:
    r = h.client.post(f"/api/v1/orders/{cid}/{action}", headers=h.auth)
    assert r.status_code == expect, r.text
    return dict(r.json())


def approved(h: Harness) -> str:
    o = propose(h)
    assert o["state"] == "AWAITING_HUMAN_APPROVAL", o["risk_reasons"]
    assert act(h, o["id"], "approve")["state"] == "APPROVED"
    return str(o["id"])


def fills(h: Harness) -> list[dict[str, Any]]:
    return list(h.client.get("/api/v1/fills").json())


# --- read-side contract ------------------------------------------------------------------
def test_system_endpoints(harness: Harness) -> None:
    h = harness
    assert h.client.get("/health").json()["status"] == "ok"
    modes = h.client.get("/api/v1/system/modes").json()
    assert modes["live_execution_available"] is False
    assert modes["default_mode"] == "SIM"
    assert "LIVE_DISABLED" not in modes["executable_modes"]
    conns = {c["name"]: c["status"] for c in h.client.get("/api/v1/connections").json()}
    assert conns["MT5 terminal (native MCP)"] == "NOT CONNECTED"
    assert conns["TradingView"] == "MANUAL ONLY"
    accts = h.client.get("/api/v1/accounts").json()
    assert [a["mode"] for a in accts] == ["SIM"]
    assert accts[0]["login_masked"] == "******001"
    assert "login" not in accts[0]
    strategies = h.client.get("/api/v1/strategies").json()
    assert len(strategies) == 6 and not any(s["implemented"] for s in strategies)


def test_writes_require_operator_token(harness: Harness) -> None:
    h = harness
    assert h.client.post("/api/v1/orders/proposals", json=BUY).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert h.client.post("/api/v1/orders/proposals", json=BUY, headers=bad).status_code == 401
    assert h.client.put("/api/v1/risk/kill-switch", json={"engaged": True}).status_code == 401


@pytest.mark.parametrize("mode", ["MT5_DEMO", "LIVE_DISABLED", "TRADINGVIEW_PAPER_MANUAL"])
def test_non_sim_modes_cannot_take_orders(harness: Harness, mode: str) -> None:
    r = harness.client.post("/api/v1/orders/proposals", json={**BUY, "account_mode": mode},
                            headers=harness.auth)
    assert r.status_code == 409


# --- lifecycle ---------------------------------------------------------------------------
def test_full_sim_lifecycle(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    o = act(h, cid, "submit")
    assert o["state"] == "ACKED" and o["fill_price"] is not None
    assert [f["entry"] for f in fills(h)] == ["IN"]
    o = act(h, cid, "reconcile")
    assert o["state"] == "RECONCILED" and o["outcome"] == "FILLED"

    r = h.client.post(f"/api/v1/sim/positions/{o['position_id']}/close",
                      json={"confirm": True},
                      headers={**h.auth, "Idempotency-Key": secrets.token_urlsafe(24)})
    assert r.status_code == 200, r.text
    assert sorted(f["entry"] for f in fills(h)) == ["IN", "OUT"]
    assert all(f["source"] == "SIMULATED" for f in fills(h))
    assert h.client.get("/api/v1/audit/verify").json() == {"ok": True, "first_bad_id": None}


def test_close_requires_explicit_confirmation(harness: Harness) -> None:
    h = harness
    o = act(h, approved(h), "submit")
    r = h.client.post(f"/api/v1/sim/positions/{o['position_id']}/close",
                      json={"confirm": False},
                      headers={**h.auth, "Idempotency-Key": secrets.token_urlsafe(24)})
    assert r.status_code == 400
    assert len(h.sim.get_positions()) == 1


def test_duplicate_submit_is_refused(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    act(h, cid, "submit")
    act(h, cid, "submit", expect=409)
    assert len(fills(h)) == 1


def test_cannot_submit_without_approval(harness: Harness) -> None:
    h = harness
    o = propose(h)
    act(h, o["id"], "submit", expect=409)
    assert fills(h) == []


def test_expired_approval_cannot_submit(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    h.clock.advance(61)
    assert act(h, cid, "submit")["state"] == "EXPIRED"
    assert fills(h) == []


def test_missing_stop_loss_rejected(harness: Harness) -> None:
    h = harness
    r = h.client.post("/api/v1/orders/proposals", json={**BUY, "sl": None}, headers=h.auth)
    o = r.json()
    assert o["state"] == "REJECTED" and any("stop loss" in x for x in o["risk_reasons"])


def test_excess_risk_rejected(harness: Harness) -> None:
    o = propose(harness, volume="1.00", sl="2000.00")
    assert o["state"] == "REJECTED"
    assert any("exceeds max" in x for x in o["risk_reasons"])


def test_kill_switch_blocks_new_and_approved_orders(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    assert h.client.put("/api/v1/risk/kill-switch", json={"engaged": True},
                        headers=h.auth).json() == {"engaged": True}
    o = act(h, cid, "submit")
    assert o["state"] == "REJECTED" and any("kill switch" in x for x in o["risk_reasons"])
    assert propose(h)["state"] == "REJECTED"
    assert fills(h) == []
    h.client.put("/api/v1/risk/kill-switch", json={"engaged": False}, headers=h.auth)
    assert propose(h)["state"] == "AWAITING_HUMAN_APPROVAL"


def test_account_change_between_approval_and_send_blocks(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    h.sim.identity = h.sim.identity.model_copy(update={"login": "SIM000777"})
    o = act(h, cid, "submit")
    assert o["state"] == "REJECTED"
    assert any("identity changed" in x for x in o["risk_reasons"])
    assert fills(h) == []


def test_unregistered_account_blocks_proposal(harness: Harness) -> None:
    h = harness
    h.sim.identity = h.sim.identity.model_copy(update={"login": "SIM000777"})
    o = propose(h)
    assert o["state"] == "REJECTED"
    assert any("identity changed" in x for x in o["risk_reasons"])


def test_stale_heartbeat_blocks(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    h.sim.heartbeat_frozen_at = h.clock.now - timedelta(seconds=120)
    o = act(h, cid, "submit")
    assert o["state"] == "REJECTED" and any("stale" in x for x in o["risk_reasons"])


def test_disconnect_blocks(harness: Harness) -> None:
    h = harness
    h.sim.connected = False
    assert propose(h)["state"] == "REJECTED"


def test_broker_rejection(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    h.sim.inject_next_submit = "reject"
    o = act(h, cid, "submit")
    assert o["state"] == "REJECTED" and o["outcome"] == "BROKER_REJECTED"


def test_unknown_outcome_reconciles_to_fill_without_duplicate(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    h.sim.inject_next_submit = "timeout_filled"
    assert act(h, cid, "submit")["state"] == "UNKNOWN"
    act(h, cid, "submit", expect=409)  # no blind resubmit from UNKNOWN
    o = act(h, cid, "reconcile")
    assert o["state"] == "RECONCILED" and o["outcome"] == "FILLED"
    assert o["broker_order_id"] is not None
    assert len(fills(h)) == 1


def test_unknown_outcome_reconciles_to_not_placed(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    h.sim.inject_next_submit = "timeout_not_placed"
    assert act(h, cid, "submit")["state"] == "UNKNOWN"
    o = act(h, cid, "reconcile")
    assert o["state"] == "RECONCILED" and o["outcome"] == "NOT_PLACED"
    assert fills(h) == []


def test_order_event_history_is_recorded(harness: Harness) -> None:
    h = harness
    cid = approved(h)
    act(h, cid, "submit")
    with h.engine.connect() as c:
        states = [r[0] for r in c.execute(
            text("SELECT to_state FROM order_events WHERE command_id=:c ORDER BY id"),
            {"c": cid})]
    assert states == ["DRAFT", "RISK_CHECKED", "AWAITING_HUMAN_APPROVAL", "APPROVED",
                      "SUBMITTING", "ACKED"]


def test_audit_tampering_detected(harness: Harness) -> None:
    h = harness
    approved(h)
    if h.backend == "postgres":
        with pytest.raises(DBAPIError, match="append-only"), h.engine.begin() as c:
            c.execute(text("UPDATE audit_log SET actor='mallory' WHERE id=1"))
        return
    with h.engine.begin() as c:
        c.execute(text("UPDATE audit_log SET actor='mallory' WHERE id=1"))
    assert h.client.get("/api/v1/audit/verify").json() == {"ok": False, "first_bad_id": 1}


@pytest.mark.postgres
def test_fills_are_append_only_in_postgres(harness: Harness) -> None:
    h = harness
    if h.backend != "postgres":
        pytest.skip("trigger is PostgreSQL-only")
    act(h, approved(h), "submit")
    for stmt in ("UPDATE fills SET profit = 999", "DELETE FROM fills",
                 "DELETE FROM order_events"):
        with pytest.raises(DBAPIError, match="append-only"), h.engine.begin() as c:
            c.execute(text(stmt))


def test_lifecycle_with_real_wall_clock(backend: str) -> None:
    """Regression: with a real clock the quote is stamped after `now` was read."""
    from fastapi.testclient import TestClient
    from tsch_api.brokers.sim import SimBroker
    from tsch_api.config import Settings
    from tsch_api.db import make_engine
    from tsch_api.main import create_app

    from ..conftest import TOKEN

    if backend != "sqlite":
        pytest.skip("wall-clock regression only needs one backend")
    app = create_app(Settings(database_url="unused://", operator_token=TOKEN),
                     engine=make_engine("sqlite://"), sim=SimBroker(), create_schema=True)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app) as c:
        bid = app.state.sim.get_quote("XAUUSD").bid
        r = c.post("/api/v1/orders/proposals", headers=auth,
                   json={**BUY, "sl": str(bid - 10)}).json()
        assert r["state"] == "AWAITING_HUMAN_APPROVAL", r["risk_reasons"]
        assert c.post(f"/api/v1/orders/{r['id']}/approve", headers=auth).json()["state"] == \
            "APPROVED"
        assert c.post(f"/api/v1/orders/{r['id']}/submit", headers=auth).json()["state"] == \
            "ACKED"
