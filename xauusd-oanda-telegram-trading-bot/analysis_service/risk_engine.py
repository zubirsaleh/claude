"""Risk engine: stop-loss, targets, risk/reward and position sizing.

All maths are derived from the supplied price/indicator data. Output is
advisory only by default. No order is ever placed here.
"""
from __future__ import annotations

from shared.models import RiskPlan

_ATR_SL_MULT = 1.5


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def build_plan(
    bias: str,
    entry: float,
    indicators: dict,
    account_balance: float,
    risk_percent: float,
) -> RiskPlan | None:
    """Build a stop-loss/target/position-size plan for the given bias.

    Returns ``None`` for a WAIT bias (no actionable trade).
    """
    if bias not in ("LONG", "SHORT"):
        return None

    atr = indicators.get("atr_14") or 0.0
    support = indicators.get("support")
    resistance = indicators.get("resistance")

    if bias == "LONG":
        atr_stop = entry - _ATR_SL_MULT * atr
        # Stop below recent swing low (support) or 1.5 ATR, whichever is lower.
        stop_loss = min(atr_stop, support) if support else atr_stop
        risk_per_unit = entry - stop_loss
        target_1 = resistance if resistance and resistance > entry else entry + risk_per_unit
        target_2 = max(entry + 2 * risk_per_unit, target_1 + risk_per_unit)
    else:  # SHORT
        atr_stop = entry + _ATR_SL_MULT * atr
        stop_loss = max(atr_stop, resistance) if resistance else atr_stop
        risk_per_unit = stop_loss - entry
        target_1 = support if support and support < entry else entry - risk_per_unit
        target_2 = min(entry - 2 * risk_per_unit, target_1 - risk_per_unit)

    risk_per_unit = abs(risk_per_unit)
    if risk_per_unit <= 0:
        return None

    reward = abs(target_1 - entry)
    risk_reward = round(_safe_div(reward, risk_per_unit), 2)

    risk_amount = account_balance * risk_percent / 100.0
    position_size = round(_safe_div(risk_amount, risk_per_unit), 4)

    return RiskPlan(
        entry=round(entry, 3),
        stop_loss=round(stop_loss, 3),
        target_1=round(target_1, 3),
        target_2=round(target_2, 3),
        risk_reward=risk_reward,
        risk_per_unit=round(risk_per_unit, 3),
        risk_amount=round(risk_amount, 2),
        position_size=position_size,
        account_balance=round(account_balance, 2),
        risk_percent=risk_percent,
    )
