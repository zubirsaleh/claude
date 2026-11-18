"""The only path to the broker. Every order: fresh broker state -> risk gate -> send."""
from __future__ import annotations

from datetime import datetime, timezone

from scalper.broker_oanda import BrokerError, OandaClient
from scalper.journal import Journal
from scalper.risk import Decision, MarketSnapshot, OrderRequest, RiskEngine


class Executor:
    def __init__(self, broker: OandaClient, risk: RiskEngine, journal: Journal) -> None:
        self.broker = broker
        self.risk = risk
        self.journal = journal

    def _snapshot(self, news_events: list[datetime]) -> MarketSnapshot:
        quote = self.broker.quote()
        if not quote.tradeable:
            raise BrokerError("instrument not tradeable")
        return MarketSnapshot(
            bid=quote.bid, ask=quote.ask, quote_time=quote.time,
            equity=self.broker.equity(),
            open_positions=self.broker.open_position_count(),
            news_events=news_events,
        )

    def submit(self, order: OrderRequest, news_events: list[datetime] | None = None) -> Decision:
        now = datetime.now(timezone.utc)
        if self.risk.state.kill_switch:
            decision = Decision(False, [f"kill switch active: {self.risk.state.kill_reason}"])
            self.journal.log("order_denied", order=order, reasons=decision.reasons)
            return decision
        try:
            mkt = self._snapshot(news_events or [])
            self.risk.record_api_ok()
        except BrokerError as exc:
            self.risk.record_api_error()
            self.journal.log("order_denied", order=order, reasons=[f"broker state: {exc}"])
            return Decision(False, [f"broker state unavailable: {exc}"])

        decision = self.risk.check_order(order, mkt, now)
        self.journal.log("risk_check", order=order, market=mkt, decision=decision)
        if not decision.allowed:
            return decision

        try:
            result = self.broker.market_order(
                order.side, order.units, order.stop_price, order.take_profit_price
            )
            self.risk.record_api_ok()
        except BrokerError as exc:
            self.risk.record_api_error()
            self.journal.log("order_error", order=order, error=str(exc))
            return Decision(False, [f"order failed: {exc}"])

        self.risk.record_order_placed()
        self.journal.log("order_sent", order=order, result=result)
        if "orderFillTransaction" not in result:
            self.journal.log("order_not_filled", result=result)
            return Decision(False, ["order not filled (FOK cancelled)"])
        return decision

    def kill(self, reason: str) -> None:
        self.risk.trip_kill_switch(reason)
        self.journal.log("kill_switch", reason=reason)
        try:
            closed = self.broker.close_all()
            self.journal.log("positions_closed", result=closed)
        except BrokerError as exc:
            self.journal.log("close_all_failed", error=str(exc))
            raise
