"""Broker-independent domain models.

Money and prices are Decimal throughout; timestamps are timezone-aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountMode(StrEnum):
    SIM = "SIM"
    MT5_DEMO = "MT5_DEMO"
    TRADINGVIEW_PAPER_MANUAL = "TRADINGVIEW_PAPER_MANUAL"
    LIVE_DISABLED = "LIVE_DISABLED"


class AccountType(StrEnum):
    DEMO = "DEMO"
    REAL = "REAL"
    CONTEST = "CONTEST"
    UNKNOWN = "UNKNOWN"


class DataSource(StrEnum):
    BROKER_MT5 = "BROKER_MT5"
    SIMULATED = "SIMULATED"
    MANUAL_TRADE_JOURNAL = "MANUAL_TRADE_JOURNAL"
    PERSONAL_TV_DISPLAY = "PERSONAL_TV_DISPLAY"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Timeframe(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_utc(v: datetime) -> datetime:
    if v.tzinfo is None or v.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return v.astimezone(UTC)


class BrokerIdentity(_Frozen):
    broker: str
    server: str
    login: str
    account_type: AccountType
    mode: AccountMode
    currency: str = Field(min_length=3, max_length=3)
    trade_allowed: bool

    @property
    def masked_login(self) -> str:
        if len(self.login) <= 3:
            return "*" * len(self.login)
        return "*" * (len(self.login) - 3) + self.login[-3:]

    def same_account(self, other: BrokerIdentity) -> bool:
        return (
            self.broker == other.broker
            and self.server == other.server
            and self.login == other.login
            and self.account_type == other.account_type
            and self.mode == other.mode
        )


class HealthStatus(_Frozen):
    connected: bool
    last_heartbeat_utc: datetime | None
    detail: str = ""

    _utc = field_validator("last_heartbeat_utc")(
        lambda v: v if v is None else _require_utc(v)
    )


class SymbolSpecs(_Frozen):
    """Broker-supplied contract specification. Never assume values across brokers."""

    symbol: str
    digits: int = Field(ge=0, le=10)
    point: Decimal = Field(gt=0)
    tick_size: Decimal = Field(gt=0)
    tick_value: Decimal = Field(gt=0, description="Account currency per 1 lot per 1 tick of loss")
    contract_size: Decimal = Field(gt=0)
    volume_min: Decimal = Field(gt=0)
    volume_max: Decimal = Field(gt=0)
    volume_step: Decimal = Field(gt=0)
    stop_level_points: int = Field(ge=0)
    freeze_level_points: int = Field(ge=0)
    currency_profit: str
    currency_margin: str


class Quote(_Frozen):
    symbol: str
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    ts_utc: datetime

    _utc = field_validator("ts_utc")(_require_utc)


class Bar(_Frozen):
    symbol: str
    timeframe: Timeframe
    ts_utc: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: int = Field(ge=0)
    source: DataSource

    _utc = field_validator("ts_utc")(_require_utc)


class AccountState(_Frozen):
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    currency: str
    ts_utc: datetime


class Position(_Frozen):
    position_id: str
    symbol: str
    side: Side
    volume: Decimal
    price_open: Decimal
    sl: Decimal | None
    tp: Decimal | None
    opened_utc: datetime
    client_id: str | None = None


class BrokerOrder(_Frozen):
    order_id: str
    symbol: str
    side: Side
    volume: Decimal
    state: str
    client_id: str | None = None


class Fill(_Frozen):
    """Immutable broker deal/fill record as observed. Sign conventions follow the broker."""

    deal_id: str
    order_id: str
    position_id: str
    symbol: str
    side: Side
    entry: str = Field(description="IN | OUT | INOUT")
    volume: Decimal
    price: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal
    profit: Decimal
    currency: str
    ts_utc: datetime
    client_id: str | None
    source: DataSource

    _utc = field_validator("ts_utc")(_require_utc)


class OrderProposal(_Frozen):
    account_mode: AccountMode
    symbol: str
    side: Side
    volume: Decimal = Field(gt=0)
    sl: Decimal | None
    tp: Decimal | None
    strategy_id: str
    strategy_version: str
    reason: str = ""


class ApprovedOrder(_Frozen):
    proposal: OrderProposal
    idempotency_key: str = Field(min_length=16)
    identity: BrokerIdentity
    approved_by: str
    approved_utc: datetime
    expires_utc: datetime
    risk_snapshot_hash: str


class ReceiptStatus(StrEnum):
    ACKED = "ACKED"
    REJECTED = "REJECTED"


class BrokerReceipt(_Frozen):
    status: ReceiptStatus
    idempotency_key: str
    broker_order_id: str | None = None
    deal_id: str | None = None
    position_id: str | None = None
    fill_price: Decimal | None = None
    message: str = ""


class ReconciliationReport(_Frozen):
    ts_utc: datetime
    positions: list[Position]
    open_orders: list[BrokerOrder]
    fills_seen: int
    receipts_by_client_id: dict[str, BrokerReceipt]
