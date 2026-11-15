from decimal import Decimal as D

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tsch_api.brokers.sim import SIM_SPECS
from tsch_risk import SizingError, compute_volume, is_valid_volume, loss_at_stop

XAU = SIM_SPECS["XAUUSD"]
EUR = SIM_SPECS["EURUSD"]


def test_xauusd_cfd_sizing_uses_broker_tick_value() -> None:
    # $5.00 stop on a 100oz CFD = 500 ticks x $1/tick/lot = $500 per lot. 1% of 10k = $100.
    r = compute_volume(D("10000"), D("1"), D("2400.00"), D("2395.00"), XAU)
    assert r.loss_per_lot == D("500")
    assert r.volume == D("0.20")
    assert r.loss_at_stop == D("100")


def test_eurusd_sizing() -> None:
    # 20 pips = 200 points; $1 per point per lot -> $200/lot; 0.5% of 10k = $50 -> 0.25 lots.
    r = compute_volume(D("10000"), D("0.5"), D("1.08000"), D("1.07800"), EUR)
    assert r.volume == D("0.25")


def test_volume_is_floored_not_rounded() -> None:
    # $100 / $300 per lot = 0.333.. -> 0.33, never 0.34 (which would exceed the allowance)
    r = compute_volume(D("10000"), D("1"), D("2400.00"), D("2397.00"), XAU)
    assert r.volume == D("0.33")
    assert r.loss_at_stop <= r.risk_amount


def test_below_broker_minimum_is_rejected_not_rounded_up() -> None:
    with pytest.raises(SizingError, match="below broker minimum"):
        compute_volume(D("100"), D("0.1"), D("2400.00"), D("2300.00"), XAU)


@pytest.mark.parametrize("pct", [D("2.01"), D("5"), D("0"), D("-1")])
def test_risk_pct_bounds(pct: D) -> None:
    with pytest.raises(SizingError):
        compute_volume(D("10000"), pct, D("2400"), D("2390"), XAU)


def test_user_cap_lower_than_hard_cap() -> None:
    with pytest.raises(SizingError, match="exceeds cap"):
        compute_volume(D("10000"), D("1"), D("2400"), D("2390"), XAU, max_risk_pct=D("0.5"))


def test_user_cap_cannot_raise_hard_cap() -> None:
    with pytest.raises(SizingError, match="exceeds cap"):
        compute_volume(D("10000"), D("3"), D("2400"), D("2390"), XAU, max_risk_pct=D("10"))


def test_zero_stop_distance_rejected() -> None:
    with pytest.raises(SizingError):
        compute_volume(D("10000"), D("1"), D("2400"), D("2400"), XAU)


def test_stop_inside_broker_stop_level_rejected() -> None:
    spec = XAU.model_copy(update={"stop_level_points": 100})
    with pytest.raises(SizingError, match="stop level"):
        compute_volume(D("10000"), D("1"), D("2400.00"), D("2399.50"), spec)


@given(
    equity=st.decimals(min_value=500, max_value=10_000_000, places=2),
    risk_bp=st.integers(min_value=1, max_value=200),
    stop_ticks=st.integers(min_value=1, max_value=50_000),
)
def test_sizing_properties(equity: D, risk_bp: int, stop_ticks: int) -> None:
    pct = D(risk_bp) / D(100)
    entry = D("2400.00")
    stop = entry - XAU.tick_size * stop_ticks
    try:
        r = compute_volume(equity, pct, entry, stop, XAU)
    except SizingError:
        allowance = equity * pct / 100
        assert allowance / loss_at_stop(entry, stop, D(1), XAU) < XAU.volume_min
        return
    assert is_valid_volume(r.volume, XAU)
    assert r.loss_at_stop <= r.risk_amount
    if r.volume < XAU.volume_max:
        bigger = r.volume + XAU.volume_step
        assert loss_at_stop(entry, stop, bigger, XAU) > r.risk_amount
