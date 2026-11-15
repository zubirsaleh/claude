"""Position sizing from broker symbol specs.

volume = allowed_loss / (abs(entry - stop) / tick_size * tick_value_per_lot)

The result is floored to the broker's volume step so the realised risk never exceeds the
allowance. A volume below the broker minimum is rejected, never rounded up.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from tsch_contracts import SymbolSpecs

ABSOLUTE_MAX_RISK_PCT = Decimal("2")


class SizingError(ValueError):
    pass


@dataclass(frozen=True)
class SizingResult:
    volume: Decimal
    risk_amount: Decimal
    loss_at_stop: Decimal
    loss_per_lot: Decimal


def loss_at_stop(entry: Decimal, stop: Decimal, volume: Decimal, spec: SymbolSpecs) -> Decimal:
    ticks = abs(entry - stop) / spec.tick_size
    return ticks * spec.tick_value * volume


def floor_to_step(volume: Decimal, step: Decimal) -> Decimal:
    steps = (volume / step).to_integral_value(rounding=ROUND_FLOOR)
    return (steps * step).quantize(step)


def is_valid_volume(volume: Decimal, spec: SymbolSpecs) -> bool:
    if volume < spec.volume_min or volume > spec.volume_max:
        return False
    return (volume / spec.volume_step) == (volume / spec.volume_step).to_integral_value()


def compute_volume(
    equity: Decimal,
    risk_pct: Decimal,
    entry: Decimal,
    stop: Decimal,
    spec: SymbolSpecs,
    max_risk_pct: Decimal = ABSOLUTE_MAX_RISK_PCT,
) -> SizingResult:
    if equity <= 0:
        raise SizingError("equity must be positive")
    if risk_pct <= 0:
        raise SizingError("risk_pct must be positive")
    cap = min(max_risk_pct, ABSOLUTE_MAX_RISK_PCT)
    if risk_pct > cap:
        raise SizingError(f"risk_pct {risk_pct} exceeds cap {cap}")
    if entry == stop:
        raise SizingError("stop must differ from entry")
    stop_distance_points = abs(entry - stop) / spec.point
    if stop_distance_points < spec.stop_level_points:
        raise SizingError(
            f"stop distance {stop_distance_points} points is inside broker stop level "
            f"{spec.stop_level_points}"
        )

    risk_amount = equity * risk_pct / Decimal(100)
    per_lot = loss_at_stop(entry, stop, Decimal(1), spec)
    volume = floor_to_step(risk_amount / per_lot, spec.volume_step)
    if volume < spec.volume_min:
        raise SizingError(
            f"risk allowance {risk_amount} supports {risk_amount / per_lot} lots, "
            f"below broker minimum {spec.volume_min}"
        )
    volume = min(volume, floor_to_step(spec.volume_max, spec.volume_step))
    return SizingResult(
        volume=volume,
        risk_amount=risk_amount,
        loss_at_stop=loss_at_stop(entry, stop, volume, spec),
        loss_per_lot=per_lot,
    )
