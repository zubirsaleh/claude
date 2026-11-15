from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from tsch_contracts import AccountMode, Side


class ProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_mode: AccountMode
    symbol: str = Field(pattern=r"^[A-Z0-9._]{3,32}$")
    side: Side
    volume: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    sl: Decimal | None = Field(default=None, gt=0)
    tp: Decimal | None = Field(default=None, gt=0)
    strategy_id: str = Field(default="manual", max_length=64)
    strategy_version: str = Field(default="0.0.0", max_length=32)
    reason: str = Field(default="", max_length=500)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    state: str
    symbol: str
    side: str
    volume: Decimal
    sl: Decimal | None
    tp: Decimal | None
    strategy_id: str
    strategy_version: str
    reason: str
    risk_reasons: list[str]
    risk_snapshot_hash: str | None
    est_entry: Decimal | None
    est_loss_at_stop: Decimal | None
    est_risk_pct: Decimal | None
    approved_by: str | None
    approved_utc: datetime | None
    expires_utc: datetime | None
    broker_order_id: str | None
    deal_id: str | None
    position_id: str | None
    fill_price: Decimal | None
    outcome: str | None
    created_utc: datetime
    updated_utc: datetime


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: str
    broker: str
    server: str
    login_masked: str
    account_type: str
    currency: str
    label: str


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    version: str
    name: str
    description: str
    default_params: dict[str, object]
    implemented: bool


class FillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    deal_id: str
    order_id: str
    position_id: str
    symbol: str
    side: str
    entry: str
    volume: Decimal
    price: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal
    profit: Decimal
    currency: str
    ts_utc: datetime
    source: str


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts_utc: datetime
    actor: str
    action: str
    detail: dict[str, object]
    hash: str


class ConnectionStatus(BaseModel):
    name: str
    mode: AccountMode | None
    status: str
    detail: str
    last_heartbeat_utc: datetime | None = None


class ModesOut(BaseModel):
    default_mode: AccountMode
    executable_modes: list[AccountMode]
    live_execution_available: bool
    notes: dict[str, str]


class KillSwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engaged: bool


class KillSwitchOut(BaseModel):
    engaged: bool


class ClosePositionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool = Field(description="Must be true; closing is a distinct, explicit action")


class AuditVerifyOut(BaseModel):
    ok: bool
    first_bad_id: int | None
