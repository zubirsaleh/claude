"""Deterministic pre-trade risk gate.

`evaluate` is pure: same inputs give the same decision and snapshot hash. It fails closed —
any missing input or internal error yields a block, never an allow.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from tsch_contracts import (
    AccountMode,
    AccountType,
    BrokerIdentity,
    HealthStatus,
    OrderProposal,
    Quote,
    Side,
    SymbolSpecs,
)

from .sizing import ABSOLUTE_MAX_RISK_PCT, is_valid_volume, loss_at_stop

EXECUTABLE_MODES = frozenset({AccountMode.SIM, AccountMode.MT5_DEMO})


@dataclass(frozen=True)
class RiskPolicy:
    # Conservative defaults. 2% is the hard ceiling, not a recommended size.
    max_risk_pct: Decimal = Decimal("0.5")
    max_daily_loss_pct: Decimal = Decimal("2")
    max_drawdown_pct: Decimal = Decimal("5")
    max_spread_points: int = 50
    max_quote_age_s: int = 10
    max_heartbeat_age_s: int = 30
    max_clock_skew_s: int = 2
    max_open_positions: int = 3
    max_volume: Decimal = Decimal("1")
    symbol_whitelist: frozenset[str] = frozenset({"XAUUSD", "EURUSD"})
    require_sl: bool = True
    kill_switch: bool = False

    def __post_init__(self) -> None:
        if not (Decimal(0) < self.max_risk_pct <= ABSOLUTE_MAX_RISK_PCT):
            raise ValueError(f"max_risk_pct must be in (0, {ABSOLUTE_MAX_RISK_PCT}]")


@dataclass(frozen=True)
class RiskContext:
    now_utc: datetime
    identity: BrokerIdentity | None
    expected_identity: BrokerIdentity | None
    health: HealthStatus | None
    quote: Quote | None
    spec: SymbolSpecs | None
    equity: Decimal | None
    day_start_equity: Decimal | None
    peak_equity: Decimal | None
    open_positions: int | None


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...]
    entry_price: Decimal | None = None
    loss_at_stop: Decimal | None = None
    risk_pct_of_equity: Decimal | None = None
    snapshot_hash: str = ""
    checks: dict[str, bool] = field(default_factory=dict)


def _hash(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def evaluate(proposal: OrderProposal, ctx: RiskContext, policy: RiskPolicy) -> RiskDecision:
    try:
        return _evaluate(proposal, ctx, policy)
    except Exception as exc:  # noqa: BLE001 — fail closed on any defect
        return RiskDecision(allowed=False, reasons=(f"risk engine error: {exc!r}",))


def _evaluate(proposal: OrderProposal, ctx: RiskContext, policy: RiskPolicy) -> RiskDecision:
    reasons: list[str] = []
    checks: dict[str, bool] = {}

    def check(name: str, ok: bool, msg: str) -> bool:
        checks[name] = ok
        if not ok:
            reasons.append(msg)
        return ok

    check("kill_switch", not policy.kill_switch, "kill switch engaged: no new entries")
    check(
        "mode_executable",
        proposal.account_mode in EXECUTABLE_MODES,
        f"mode {proposal.account_mode} cannot execute orders",
    )

    ident, expected = ctx.identity, ctx.expected_identity
    if check("identity_present", ident is not None and expected is not None, "identity missing"):
        assert ident is not None and expected is not None
        check("identity_match", ident.same_account(expected), "broker account identity changed")
        check("account_is_demo", ident.account_type == AccountType.DEMO,
              f"account type {ident.account_type} is not DEMO")
        check("mode_match", ident.mode == proposal.account_mode,
              f"identity mode {ident.mode} != proposal mode {proposal.account_mode}")
        check("trade_allowed", ident.trade_allowed, "broker reports trading not allowed")

    h = ctx.health
    if check("health_present", h is not None, "broker health unknown"):
        assert h is not None
        check("connected", h.connected, "broker disconnected")
        hb_age = (None if h.last_heartbeat_utc is None
                  else (ctx.now_utc - h.last_heartbeat_utc).total_seconds())
        fresh = hb_age is not None and (
            -policy.max_clock_skew_s <= hb_age <= policy.max_heartbeat_age_s)
        check("heartbeat_fresh", fresh, "broker heartbeat stale")

    check("symbol_whitelisted", proposal.symbol in policy.symbol_whitelist,
          f"symbol {proposal.symbol} not whitelisted")

    q, spec = ctx.quote, ctx.spec
    entry: Decimal | None = None
    loss: Decimal | None = None
    risk_pct: Decimal | None = None
    quote_ok = check("quote_present", q is not None, "no broker quote")
    spec_ok = check("spec_present", spec is not None, "no broker symbol spec")
    if quote_ok and spec_ok:
        assert q is not None and spec is not None
        age = (ctx.now_utc - q.ts_utc).total_seconds()
        check("quote_fresh", -policy.max_clock_skew_s <= age <= policy.max_quote_age_s,
              f"quote age {age:.3f}s outside [-{policy.max_clock_skew_s}, "
              f"{policy.max_quote_age_s}]s")
        spread_pts = (q.ask - q.bid) / spec.point
        check("spread", spread_pts <= policy.max_spread_points,
              f"spread {spread_pts} pts exceeds {policy.max_spread_points}")
        check("volume_valid", is_valid_volume(proposal.volume, spec),
              f"volume {proposal.volume} invalid for broker min/max/step")
        check("volume_cap", proposal.volume <= policy.max_volume,
              f"volume {proposal.volume} exceeds policy max {policy.max_volume}")

        entry = q.ask if proposal.side == Side.BUY else q.bid
        sl, tp = proposal.sl, proposal.tp
        if sl is None:
            check("sl_present", not policy.require_sl, "stop loss required")
        else:
            correct = sl < entry if proposal.side == Side.BUY else sl > entry
            check("sl_side", correct, "stop loss on wrong side of entry")
            dist_pts = abs(entry - sl) / spec.point
            check("sl_stop_level", dist_pts >= spec.stop_level_points,
                  f"stop distance {dist_pts} pts inside broker stop level")
            loss = loss_at_stop(entry, sl, proposal.volume, spec)
        if tp is not None:
            correct = tp > entry if proposal.side == Side.BUY else tp < entry
            check("tp_side", correct, "take profit on wrong side of entry")

    eq = ctx.equity
    if check("equity_present", eq is not None and eq > 0, "equity unknown"):
        assert eq is not None
        if loss is not None:
            risk_pct = loss / eq * Decimal(100)
            check("risk_per_trade", risk_pct <= policy.max_risk_pct,
                  f"risk {risk_pct:.4f}% exceeds max {policy.max_risk_pct}%")
        elif policy.require_sl:
            check("risk_known", False, "risk at stop cannot be computed")
        if ctx.day_start_equity is not None and ctx.day_start_equity > 0:
            day_loss = (ctx.day_start_equity - eq) / ctx.day_start_equity * Decimal(100)
            check("daily_loss", day_loss < policy.max_daily_loss_pct,
                  f"daily loss {day_loss:.2f}% at/over limit")
        else:
            check("daily_loss_known", False, "day-start equity unknown")
        if ctx.peak_equity is not None and ctx.peak_equity > 0:
            dd = (ctx.peak_equity - eq) / ctx.peak_equity * Decimal(100)
            check("drawdown", dd < policy.max_drawdown_pct, f"drawdown {dd:.2f}% at/over limit")
        else:
            check("drawdown_known", False, "peak equity unknown")

    if check("positions_known", ctx.open_positions is not None, "open positions unknown"):
        assert ctx.open_positions is not None
        check("max_positions", ctx.open_positions < policy.max_open_positions,
              "max concurrent positions reached")

    snapshot = {
        "proposal": proposal.model_dump(mode="json"),
        "identity": ident.model_dump(mode="json") if ident else None,
        "quote": q.model_dump(mode="json") if q else None,
        "equity": str(eq),
        "policy": {k: str(v) for k, v in sorted(policy.__dict__.items())},
        "now": ctx.now_utc.isoformat(),
        "checks": checks,
    }
    return RiskDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
        entry_price=entry,
        loss_at_stop=loss,
        risk_pct_of_equity=risk_pct,
        snapshot_hash=_hash(snapshot),
        checks=checks,
    )
