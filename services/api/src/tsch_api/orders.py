"""Order command pipeline:

propose -> risk check -> AWAITING_HUMAN_APPROVAL -> approve (expiring, risk re-checked)
-> submit (atomic claim, identity + risk re-checked just before send) -> ACKED/REJECTED/UNKNOWN
-> reconcile by idempotency key. A command is never resubmitted.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from tsch_contracts import (
    AccountMode,
    ApprovedOrder,
    BrokerAdapter,
    BrokerIdentity,
    OrderProposal,
    OrderState,
    ReceiptStatus,
    Side,
    transition,
)
from tsch_risk import RiskContext, RiskDecision, RiskPolicy, evaluate

from .db import Account, FillRecord, OrderCommand, OrderEvent, append_audit, canonical, get_state
from .db import set_state as db_set_state
from .seed import login_hash

KILL_SWITCH_KEY = "risk.kill_switch"


class CommandNotFound(Exception):
    pass


class CommandConflict(Exception):
    pass


def _safe[T](fn: Callable[[], T]) -> T | None:
    try:
        return fn()
    except Exception:  # noqa: BLE001 — unavailable data becomes None so the gate fails closed
        return None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class OrderService:
    def __init__(
        self,
        session: Session,
        adapter: BrokerAdapter,
        policy: RiskPolicy,
        approval_ttl: timedelta,
        clock: Callable[[], datetime],
    ) -> None:
        self.s = session
        self.adapter = adapter
        self.base_policy = policy
        self.ttl = approval_ttl
        self.clock = clock

    # --- helpers -----------------------------------------------------------------------
    def policy(self) -> RiskPolicy:
        engaged = bool(get_state(self.s, KILL_SWITCH_KEY, False))
        if engaged == self.base_policy.kill_switch:
            return self.base_policy
        return RiskPolicy(**{**self.base_policy.__dict__, "kill_switch": engaged})

    def _event(self, cmd: OrderCommand, frm: str | None, to: str, actor: str,
               detail: dict[str, Any] | None = None) -> None:
        self.s.add(OrderEvent(command_id=cmd.id, from_state=frm, to_state=to, actor=actor,
                              detail=detail or {}, ts_utc=self.clock()))

    def _move(self, cmd: OrderCommand, target: OrderState, actor: str,
              detail: dict[str, Any] | None = None) -> None:
        current = OrderState(cmd.state)
        transition(current, target)
        cmd.state = target.value
        cmd.version += 1
        self._event(cmd, current.value, target.value, actor, detail)

    def get(self, command_id: str) -> OrderCommand:
        cmd = self.s.get(OrderCommand, command_id)
        if cmd is None:
            raise CommandNotFound(command_id)
        return cmd

    def _account_for_mode(self, mode: AccountMode) -> Account:
        acct = self.s.scalars(select(Account).where(Account.mode == mode.value)).first()
        if acct is None:
            raise CommandConflict(f"no registered account for mode {mode}")
        return acct

    def _track_equity(self, account_id: str, equity: Decimal | None
                      ) -> tuple[Decimal | None, Decimal | None]:
        if equity is None:
            return None, None
        # Day boundary is UTC for SIM; broker-session day boundaries arrive with Phase 3.
        day_key = f"equity.day_start.{account_id}.{self.clock().date().isoformat()}"
        peak_key = f"equity.peak.{account_id}"
        day_start = get_state(self.s, day_key)
        if day_start is None:
            db_set_state(self.s, day_key, str(equity))
            day_start = str(equity)
        peak = Decimal(get_state(self.s, peak_key, str(equity)))
        if equity > peak:
            peak = equity
        db_set_state(self.s, peak_key, str(peak))
        return Decimal(day_start), peak

    def _risk(self, proposal: OrderProposal, expected: BrokerIdentity | None,
              account_id: str) -> RiskDecision:
        a = self.adapter
        identity = _safe(a.get_identity)
        state = _safe(a.get_account_state)
        equity = state.equity if state else None
        day_start, peak = self._track_equity(account_id, equity)
        positions = _safe(a.get_positions)
        health = _safe(a.get_health)
        quote = _safe(lambda: a.get_quote(proposal.symbol))
        spec = _safe(lambda: a.get_symbol_specs(proposal.symbol))
        ctx = RiskContext(
            now_utc=self.clock(),  # read after the fetches so data ages are never negative
            identity=identity,
            expected_identity=expected,
            health=health,
            quote=quote,
            spec=spec,
            equity=equity,
            day_start_equity=day_start,
            peak_equity=peak,
            open_positions=None if positions is None else len(positions),
        )
        return evaluate(proposal, ctx, self.policy())

    def _proposal(self, cmd: OrderCommand) -> OrderProposal:
        return OrderProposal(
            account_mode=AccountMode(cmd.mode), symbol=cmd.symbol, side=Side(cmd.side),
            volume=cmd.volume, sl=cmd.sl, tp=cmd.tp, strategy_id=cmd.strategy_id,
            strategy_version=cmd.strategy_version, reason=cmd.reason,
        )

    @staticmethod
    def _record_risk(cmd: OrderCommand, d: RiskDecision) -> None:
        cmd.risk_snapshot_hash = d.snapshot_hash or None
        cmd.risk_reasons = list(d.reasons)
        cmd.est_entry = d.entry_price
        cmd.est_loss_at_stop = d.loss_at_stop
        cmd.est_risk_pct = d.risk_pct_of_equity

    # --- pipeline ----------------------------------------------------------------------
    def propose(self, proposal: OrderProposal, actor: str) -> OrderCommand:
        acct = self._account_for_mode(proposal.account_mode)
        live = _safe(self.adapter.get_identity)
        expected: BrokerIdentity | None = None
        if live is not None:
            matches = (login_hash(live.login) == acct.login_sha256 and live.broker == acct.broker
                       and live.server == acct.server and live.mode.value == acct.mode
                       and live.account_type.value == acct.account_type)
            expected = live if matches else live.model_copy(update={"login": "\x00MISMATCH"})

        cmd = OrderCommand(
            idempotency_key=secrets.token_urlsafe(24), account_id=acct.id,
            mode=proposal.account_mode.value, state=OrderState.DRAFT.value,
            symbol=proposal.symbol, side=proposal.side.value, volume=proposal.volume,
            sl=proposal.sl, tp=proposal.tp, strategy_id=proposal.strategy_id,
            strategy_version=proposal.strategy_version, reason=proposal.reason,
            identity_snapshot=expected.model_dump(mode="json") if expected else {},
            created_utc=self.clock(),
        )
        self.s.add(cmd)
        self.s.flush()
        self._event(cmd, None, OrderState.DRAFT.value, actor)

        decision = self._risk(proposal, expected, acct.id)
        self._record_risk(cmd, decision)
        if decision.allowed:
            self._move(cmd, OrderState.RISK_CHECKED, "risk-engine",
                       {"snapshot": decision.snapshot_hash})
            self._move(cmd, OrderState.AWAITING_HUMAN_APPROVAL, "system")
        else:
            self._move(cmd, OrderState.REJECTED, "risk-engine", {"reasons": list(decision.reasons)})
        append_audit(self.s, actor, "order.proposed",
                     {"command_id": cmd.id, "state": cmd.state, "reasons": cmd.risk_reasons},
                     ts=self.clock())
        self.s.commit()
        return cmd

    def _expected(self, cmd: OrderCommand) -> BrokerIdentity | None:
        snap = cmd.identity_snapshot
        return BrokerIdentity.model_validate(snap) if snap else None

    def approve(self, command_id: str, actor: str) -> OrderCommand:
        cmd = self.get(command_id)
        if cmd.state != OrderState.AWAITING_HUMAN_APPROVAL.value:
            raise CommandConflict(f"cannot approve command in state {cmd.state}")
        decision = self._risk(self._proposal(cmd), self._expected(cmd), cmd.account_id)
        self._record_risk(cmd, decision)
        if not decision.allowed:
            self._move(cmd, OrderState.REJECTED, "risk-engine",
                       {"reasons": list(decision.reasons), "at": "approval"})
        else:
            now = self.clock()
            cmd.approved_by = actor
            cmd.approved_utc = now
            cmd.expires_utc = now + self.ttl
            self._move(cmd, OrderState.APPROVED, actor,
                       {"expires_utc": cmd.expires_utc.isoformat(),
                        "snapshot": decision.snapshot_hash})
        append_audit(self.s, actor, "order.approve",
                     {"command_id": cmd.id, "state": cmd.state}, ts=self.clock())
        self.s.commit()
        return cmd

    def submit(self, command_id: str, actor: str) -> OrderCommand:
        cmd = self.get(command_id)
        if cmd.state != OrderState.APPROVED.value:
            raise CommandConflict(f"cannot submit command in state {cmd.state}")
        now = self.clock()
        expires = _aware(cmd.expires_utc)
        if expires is None or now > expires:
            self._move(cmd, OrderState.EXPIRED, "system", {"at": now.isoformat()})
            append_audit(self.s, actor, "order.expired", {"command_id": cmd.id}, ts=now)
            self.s.commit()
            return cmd

        # Atomic claim: only one caller may move APPROVED -> SUBMITTING.
        claimed = self.s.execute(
            update(OrderCommand)
            .where(OrderCommand.id == cmd.id, OrderCommand.state == OrderState.APPROVED.value,
                   OrderCommand.version == cmd.version)
            .values(state=OrderState.SUBMITTING.value, version=cmd.version + 1)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            self.s.rollback()
            raise CommandConflict("command already claimed by another submit")
        self._event(cmd, OrderState.APPROVED.value, OrderState.SUBMITTING.value, actor)
        self.s.commit()
        self.s.refresh(cmd)

        proposal = self._proposal(cmd)
        expected = self._expected(cmd)
        decision = self._risk(proposal, expected, cmd.account_id)
        if not decision.allowed:
            self._record_risk(cmd, decision)
            self._move(cmd, OrderState.REJECTED, "risk-engine",
                       {"reasons": list(decision.reasons), "at": "pre-send"})
            append_audit(self.s, actor, "order.blocked_pre_send",
                         {"command_id": cmd.id, "reasons": list(decision.reasons)}, ts=now)
            self.s.commit()
            return cmd
        assert expected is not None and expires is not None and cmd.approved_utc is not None

        approved = ApprovedOrder(
            proposal=proposal, idempotency_key=cmd.idempotency_key, identity=expected,
            approved_by=cmd.approved_by or actor, approved_utc=_aware(cmd.approved_utc) or now,
            expires_utc=expires, risk_snapshot_hash=decision.snapshot_hash,
        )
        try:
            receipt = self.adapter.submit_approved_demo_order(approved)
        except Exception as exc:  # noqa: BLE001 — any failure means outcome unknown
            self._move(cmd, OrderState.UNKNOWN, "broker", {"error": repr(exc)})
            append_audit(self.s, actor, "order.unknown",
                         {"command_id": cmd.id, "error": repr(exc)}, ts=self.clock())
            self.s.commit()
            return cmd

        if receipt.status == ReceiptStatus.ACKED:
            cmd.broker_order_id = receipt.broker_order_id
            cmd.deal_id = receipt.deal_id
            cmd.position_id = receipt.position_id
            cmd.fill_price = receipt.fill_price
            self._move(cmd, OrderState.ACKED, "broker", {"order_id": receipt.broker_order_id})
        else:
            cmd.outcome = "BROKER_REJECTED"
            self._move(cmd, OrderState.REJECTED, "broker", {"message": receipt.message})
        append_audit(self.s, actor, "order.submitted",
                     {"command_id": cmd.id, "state": cmd.state}, ts=self.clock())
        self.s.commit()
        self.ingest_fills(cmd.account_id)
        return cmd

    def reconcile(self, command_id: str, actor: str) -> OrderCommand:
        cmd = self.get(command_id)
        if cmd.state == OrderState.SUBMITTING.value:
            # Crash between claim and broker response: treat as unknown, then look it up.
            self._move(cmd, OrderState.UNKNOWN, "reconciler", {"from": "stale SUBMITTING"})
        if cmd.state not in (OrderState.UNKNOWN.value, OrderState.ACKED.value):
            raise CommandConflict(f"nothing to reconcile in state {cmd.state}")

        self.ingest_fills(cmd.account_id)
        receipt = self.adapter.find_by_client_id(cmd.idempotency_key)
        fill = self.s.scalars(select(FillRecord).where(
            FillRecord.client_id == cmd.idempotency_key, FillRecord.entry == "IN")).first()

        if cmd.state == OrderState.UNKNOWN.value:
            if receipt is not None and receipt.status == ReceiptStatus.ACKED:
                cmd.broker_order_id = receipt.broker_order_id
                cmd.deal_id = receipt.deal_id
                cmd.position_id = receipt.position_id
                cmd.fill_price = receipt.fill_price
                self._move(cmd, OrderState.ACKED, "reconciler", {"found": "broker receipt"})
            else:
                cmd.outcome = "BROKER_REJECTED" if receipt else "NOT_PLACED"
                self._move(cmd, OrderState.RECONCILED, "reconciler", {"outcome": cmd.outcome})

        if cmd.state == OrderState.ACKED.value:
            if fill is None:
                self.s.commit()
                raise CommandConflict("broker acknowledged but fill not yet observed")
            cmd.outcome = "FILLED"
            self._move(cmd, OrderState.RECONCILED, "reconciler", {"deal_id": fill.deal_id})
        append_audit(self.s, actor, "order.reconciled",
                     {"command_id": cmd.id, "outcome": cmd.outcome}, ts=self.clock())
        self.s.commit()
        return cmd

    def ingest_fills(self, account_id: str) -> int:
        cursor_key = f"fills.cursor.{account_id}"
        cursor = int(get_state(self.s, cursor_key, 0))
        fills, new_cursor = self.adapter.get_fills(cursor)
        added = 0
        for f in fills:
            raw = f.model_dump(mode="json")
            h = hashlib.sha256(canonical({"account": account_id, **raw}).encode()).hexdigest()
            if self.s.scalars(select(FillRecord.id).where(FillRecord.payload_hash == h)).first():
                continue
            self.s.add(FillRecord(
                account_id=account_id, deal_id=f.deal_id, order_id=f.order_id,
                position_id=f.position_id, symbol=f.symbol, side=f.side.value, entry=f.entry,
                volume=f.volume, price=f.price, commission=f.commission, swap=f.swap,
                fee=f.fee, profit=f.profit, currency=f.currency, ts_utc=f.ts_utc,
                client_id=f.client_id, source=f.source.value, payload_hash=h, raw=raw,
            ))
            added += 1
        db_set_state(self.s, cursor_key, new_cursor)
        self.s.commit()
        return added

    def set_kill_switch(self, engaged: bool, actor: str) -> None:
        db_set_state(self.s, KILL_SWITCH_KEY, engaged)
        append_audit(self.s, actor, "risk.kill_switch", {"engaged": engaged}, ts=self.clock())
        self.s.commit()
