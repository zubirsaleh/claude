"""BrokerAdapter contract (ARCHITECTURE_AND_REQUIREMENTS.md §D).

Implementations: SIM (services/api) and MT5_DEMO (Phase 4, via services/mt5-agent).
There is deliberately no LIVE implementation and no TradingView implementation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from .models import (
    AccountState,
    ApprovedOrder,
    Bar,
    BrokerIdentity,
    BrokerOrder,
    BrokerReceipt,
    Fill,
    HealthStatus,
    Position,
    Quote,
    ReconciliationReport,
    SymbolSpecs,
    Timeframe,
)


class BrokerError(Exception):
    """Base for adapter failures."""


class BrokerNotConnected(BrokerError):
    pass


class BrokerTimeout(BrokerError):
    """The outcome of a submit is unknown. Callers must reconcile, never resubmit blindly."""


class LiveTradingDisabled(BrokerError):
    """Raised for any attempt to obtain or use a live execution path."""


@runtime_checkable
class BrokerAdapter(Protocol):
    def get_identity(self) -> BrokerIdentity: ...

    def get_health(self) -> HealthStatus: ...

    def get_account_state(self) -> AccountState: ...

    def get_symbol_specs(self, symbol: str) -> SymbolSpecs: ...

    def get_quote(self, symbol: str) -> Quote: ...

    def get_candles(
        self, symbol: str, timeframe: Timeframe, start_utc: datetime, end_utc: datetime
    ) -> list[Bar]: ...

    def get_positions(self) -> list[Position]: ...

    def get_open_orders(self) -> list[BrokerOrder]: ...

    def get_fills(self, cursor: int = 0) -> tuple[list[Fill], int]: ...

    def submit_approved_demo_order(self, order: ApprovedOrder) -> BrokerReceipt: ...

    def close_demo_position(self, position_id: str, idempotency_key: str) -> BrokerReceipt: ...

    def find_by_client_id(self, idempotency_key: str) -> BrokerReceipt | None: ...

    def reconcile(self) -> ReconciliationReport: ...
