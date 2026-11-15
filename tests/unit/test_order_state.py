import pytest
from tsch_contracts import IllegalTransition, OrderState, transition
from tsch_contracts.order_state import TERMINAL, TRANSITIONS

S = OrderState


def test_happy_path_is_legal() -> None:
    path = [S.DRAFT, S.RISK_CHECKED, S.AWAITING_HUMAN_APPROVAL, S.APPROVED, S.SUBMITTING,
            S.ACKED, S.RECONCILED]
    for a, b in zip(path, path[1:], strict=False):
        assert transition(a, b) == b


@pytest.mark.parametrize("src,dst", [
    (S.DRAFT, S.APPROVED),                    # cannot skip risk + human approval
    (S.RISK_CHECKED, S.SUBMITTING),           # cannot skip approval
    (S.AWAITING_HUMAN_APPROVAL, S.SUBMITTING),
    (S.UNKNOWN, S.SUBMITTING),                # never blindly resubmit
    (S.UNKNOWN, S.APPROVED),
    (S.EXPIRED, S.SUBMITTING),                # expired approvals cannot submit
    (S.REJECTED, S.AWAITING_HUMAN_APPROVAL),
    (S.ACKED, S.SUBMITTING),
])
def test_illegal_transitions(src: OrderState, dst: OrderState) -> None:
    with pytest.raises(IllegalTransition):
        transition(src, dst)


def test_terminal_states_have_no_exits() -> None:
    assert TERMINAL == {S.REJECTED, S.RECONCILED, S.EXPIRED, S.CANCELLED}
    for s in TERMINAL:
        assert not TRANSITIONS[s]


def test_every_state_reaches_a_terminal_state() -> None:
    for start in S:
        seen, frontier = {start}, [start]
        while frontier:
            for nxt in TRANSITIONS[frontier.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        assert seen & TERMINAL, start
