"""Order/approval command state machine (ARCHITECTURE_AND_REQUIREMENTS.md §D)."""

from __future__ import annotations

from enum import StrEnum


class OrderState(StrEnum):
    DRAFT = "DRAFT"
    SIGNAL_ONLY = "SIGNAL_ONLY"
    RISK_CHECKED = "RISK_CHECKED"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    APPROVED = "APPROVED"
    SUBMITTING = "SUBMITTING"
    ACKED = "ACKED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


S = OrderState

TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    S.DRAFT: frozenset({S.SIGNAL_ONLY, S.RISK_CHECKED, S.REJECTED, S.CANCELLED}),
    S.SIGNAL_ONLY: frozenset({S.RISK_CHECKED, S.REJECTED, S.CANCELLED}),
    S.RISK_CHECKED: frozenset({S.AWAITING_HUMAN_APPROVAL, S.REJECTED}),
    S.AWAITING_HUMAN_APPROVAL: frozenset({S.APPROVED, S.REJECTED, S.EXPIRED, S.CANCELLED}),
    S.APPROVED: frozenset({S.SUBMITTING, S.REJECTED, S.EXPIRED, S.CANCELLED}),
    # SUBMITTING -> REJECTED covers both broker rejects and pre-send risk re-check failures.
    S.SUBMITTING: frozenset({S.ACKED, S.REJECTED, S.UNKNOWN}),
    # UNKNOWN may only be resolved by reconciliation against broker identifiers.
    S.UNKNOWN: frozenset({S.ACKED, S.RECONCILED}),
    S.ACKED: frozenset({S.RECONCILED}),
    S.REJECTED: frozenset(),
    S.RECONCILED: frozenset(),
    S.EXPIRED: frozenset(),
    S.CANCELLED: frozenset(),
}

TERMINAL = frozenset(s for s, nxt in TRANSITIONS.items() if not nxt)


class IllegalTransition(Exception):
    def __init__(self, current: OrderState, target: OrderState) -> None:
        super().__init__(f"illegal order transition {current} -> {target}")
        self.current = current
        self.target = target


def transition(current: OrderState, target: OrderState) -> OrderState:
    if target not in TRANSITIONS[current]:
        raise IllegalTransition(current, target)
    return target
