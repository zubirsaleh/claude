"""Deterministic pre-trade risk gate. No AI model can bypass it.

Every order must pass `RiskEngine.check_order`. Any unexpected condition or
exception denies the order (fail closed). State is persisted so a restart
cannot clear the kill switch, daily loss lock or peak equity.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from scalper import sessions
from scalper.settings import LIMITS, RiskLimits


@dataclass(frozen=True)
class OrderRequest:
    side: str  # "BUY" or "SELL"
    units: int
    stop_price: float | None
    take_profit_price: float | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    bid: float
    ask: float
    quote_time: datetime
    equity: float
    open_positions: int
    news_events: list[datetime] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reasons: list[str]


@dataclass
class RiskState:
    peak_equity: float
    day_start_equity: float
    trading_day: str = ""
    trades_today: int = 0
    consecutive_losses: int = 0
    loss_streak_session: str = ""
    consecutive_api_errors: int = 0
    kill_switch: bool = False
    kill_reason: str = ""


class RiskEngine:
    def __init__(self, state_path: Path, limits: RiskLimits = LIMITS) -> None:
        self.limits = limits
        self.state_path = Path(state_path)
        self.state = self._load()

    def _load(self) -> RiskState:
        if self.state_path.exists():
            return RiskState(**json.loads(self.state_path.read_text()))
        eq = self.limits.account_size_usd
        return RiskState(peak_equity=eq, day_start_equity=eq)

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.state_path.parent)
        with os.fdopen(fd, "w") as f:
            json.dump(asdict(self.state), f)
        os.replace(tmp, self.state_path)

    def trip_kill_switch(self, reason: str) -> None:
        self.state.kill_switch = True
        self.state.kill_reason = reason
        self._save()

    def reset_kill_switch(self) -> None:
        """Operator-only: call from the manual restart command, never from the agent."""
        self.state.kill_switch = False
        self.state.kill_reason = ""
        self.state.consecutive_api_errors = 0
        self._save()

    def record_api_error(self) -> None:
        self.state.consecutive_api_errors += 1
        if self.state.consecutive_api_errors >= self.limits.max_consecutive_api_errors:
            self.trip_kill_switch("too many consecutive API errors")
        self._save()

    def record_api_ok(self) -> None:
        if self.state.consecutive_api_errors:
            self.state.consecutive_api_errors = 0
            self._save()

    def record_trade_closed(self, pnl_usd: float, closed_at: datetime) -> None:
        if pnl_usd < 0:
            session = sessions.session_at(closed_at).value
            if session != self.state.loss_streak_session:
                self.state.consecutive_losses = 0
                self.state.loss_streak_session = session
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0
        self._save()

    def update_equity(self, equity: float, now: datetime) -> None:
        day = sessions.trading_day(now).isoformat()
        if day != self.state.trading_day:
            self.state.trading_day = day
            self.state.day_start_equity = equity
            self.state.trades_today = 0
            self.state.consecutive_losses = 0
        self.state.peak_equity = max(self.state.peak_equity, equity)
        dd_floor = self.state.peak_equity * (1 - self.limits.max_drawdown_pct / 100)
        if equity <= dd_floor and not self.state.kill_switch:
            self.trip_kill_switch(
                f"max drawdown {self.limits.max_drawdown_pct}% hit: equity {equity:.2f}"
            )
        self._save()

    def record_order_placed(self) -> None:
        self.state.trades_today += 1
        self._save()

    def check_order(self, order: OrderRequest, mkt: MarketSnapshot, now: datetime) -> Decision:
        try:
            return self._check(order, mkt, now)
        except Exception as exc:  # fail closed
            return Decision(False, [f"risk check error: {exc!r}"])

    def _check(self, order: OrderRequest, mkt: MarketSnapshot, now: datetime) -> Decision:
        lim, st = self.limits, self.state
        self.update_equity(mkt.equity, now)
        reasons: list[str] = []

        if st.kill_switch:
            return Decision(False, [f"kill switch active: {st.kill_reason}"])

        daily_loss = st.day_start_equity - mkt.equity
        if daily_loss >= lim.max_daily_loss_usd:
            reasons.append(f"daily loss limit reached ({daily_loss:.2f} USD)")

        if not sessions.entries_allowed(now):
            reasons.append(f"entries not allowed in session {sessions.session_at(now).value}")
        if sessions.in_news_blackout(now, mkt.news_events, lim.news_blackout_minutes):
            reasons.append("news blackout window")

        age = (now - mkt.quote_time).total_seconds()
        if age > lim.stale_quote_seconds or age < -1:
            reasons.append(f"stale or future quote ({age:.1f}s)")
        if not (0 < mkt.bid < mkt.ask):
            reasons.append(f"invalid quote bid={mkt.bid} ask={mkt.ask}")
            return Decision(False, reasons)

        spread = mkt.ask - mkt.bid
        if spread > lim.max_spread_usd:
            reasons.append(f"spread {spread:.2f} > max {lim.max_spread_usd:.2f}")

        if order.side not in ("BUY", "SELL"):
            reasons.append(f"invalid side {order.side!r}")
            return Decision(False, reasons)
        if order.units != lim.units:
            reasons.append(f"units {order.units} != configured {lim.units}")

        entry = mkt.ask if order.side == "BUY" else mkt.bid
        if order.stop_price is None:
            reasons.append("order has no stop-loss")
        else:
            stop_dist = entry - order.stop_price if order.side == "BUY" else order.stop_price - entry
            if stop_dist <= 0:
                reasons.append("stop-loss on wrong side of entry")
            else:
                if stop_dist < lim.min_stop_to_spread_ratio * spread:
                    reasons.append(
                        f"stop {stop_dist:.2f} < {lim.min_stop_to_spread_ratio}x spread"
                    )
                risk = stop_dist * order.units
                if risk > lim.max_risk_per_trade_usd:
                    reasons.append(
                        f"trade risk {risk:.2f} > max {lim.max_risk_per_trade_usd:.2f} USD"
                    )
                remaining = lim.max_daily_loss_usd - max(daily_loss, 0)
                if risk > remaining:
                    reasons.append(
                        f"trade risk {risk:.2f} exceeds remaining daily budget {remaining:.2f}"
                    )

        if mkt.open_positions >= lim.max_open_positions:
            reasons.append("max open positions reached")
        if st.trades_today >= lim.max_trades_per_day:
            reasons.append("max trades per day reached")
        current_session = sessions.session_at(now).value
        if (
            st.consecutive_losses >= lim.max_consecutive_losses
            and st.loss_streak_session == current_session
        ):
            reasons.append(f"{st.consecutive_losses} consecutive losses: paused for session")

        return Decision(not reasons, reasons or ["ok"])
