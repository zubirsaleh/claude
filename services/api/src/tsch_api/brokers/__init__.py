"""Adapter factory. LIVE is a compiled-in refusal, not a configuration flag."""

from __future__ import annotations

from tsch_contracts import AccountMode, BrokerAdapter, BrokerNotConnected, LiveTradingDisabled

from .sim import SimBroker

LIVE_EXECUTION_COMPILED_IN = False


def make_adapter(mode: AccountMode) -> BrokerAdapter:
    if mode == AccountMode.SIM:
        return SimBroker()
    if mode == AccountMode.MT5_DEMO:
        raise BrokerNotConnected(
            "MT5_DEMO adapter not implemented until Phase 4 (requires a verified terminal)"
        )
    if mode == AccountMode.TRADINGVIEW_PAPER_MANUAL:
        raise BrokerNotConnected(
            "TradingView Paper Trading is manual only; no order adapter exists by design"
        )
    raise LiveTradingDisabled("live execution is not part of this release")


__all__ = ["LIVE_EXECUTION_COMPILED_IN", "SimBroker", "make_adapter"]
