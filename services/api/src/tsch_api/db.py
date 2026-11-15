from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

MONEY = Numeric(28, 10)


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), Decimal: MONEY}


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("mode", "broker", "server", "login_sha256"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mode: Mapped[str] = mapped_column(String(32))
    broker: Mapped[str] = mapped_column(String(128))
    server: Mapped[str] = mapped_column(String(128))
    login_masked: Mapped[str] = mapped_column(String(64))
    login_sha256: Mapped[str] = mapped_column(String(64))
    account_type: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    label: Mapped[str] = mapped_column(String(128), default="")
    created_utc: Mapped[datetime] = mapped_column(default=utcnow)


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("key", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    default_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    implemented: Mapped[bool] = mapped_column(default=False)
    created_utc: Mapped[datetime] = mapped_column(default=utcnow)


class Arm(Base):
    __tablename__ = "arms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id"))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    group_name: Mapped[str] = mapped_column(String(64), default="default")
    session: Mapped[str] = mapped_column(String(32), default="ANY")
    state: Mapped[str] = mapped_column(String(32), default="DISABLED")
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_utc: Mapped[datetime] = mapped_column(default=utcnow)
    updated_utc: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class OrderCommand(Base):
    __tablename__ = "order_commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    mode: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))
    volume: Mapped[Decimal]
    sl: Mapped[Decimal | None]
    tp: Mapped[Decimal | None]
    strategy_id: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text, default="")
    identity_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    risk_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    risk_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    est_entry: Mapped[Decimal | None]
    est_loss_at_stop: Mapped[Decimal | None]
    est_risk_pct: Mapped[Decimal | None]
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_utc: Mapped[datetime | None]
    expires_utc: Mapped[datetime | None]
    broker_order_id: Mapped[str | None] = mapped_column(String(64))
    deal_id: Mapped[str | None] = mapped_column(String(64))
    position_id: Mapped[str | None] = mapped_column(String(64))
    fill_price: Mapped[Decimal | None]
    outcome: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_utc: Mapped[datetime] = mapped_column(default=utcnow)
    updated_utc: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class OrderEvent(Base):
    """Append-only (enforced by trigger on PostgreSQL)."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command_id: Mapped[str] = mapped_column(ForeignKey("order_commands.id"), index=True)
    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ts_utc: Mapped[datetime] = mapped_column(default=utcnow)


class FillRecord(Base):
    """Immutable raw broker fill (enforced by trigger on PostgreSQL)."""

    __tablename__ = "fills"
    __table_args__ = (UniqueConstraint("account_id", "deal_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    deal_id: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[str] = mapped_column(String(64))
    position_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))
    entry: Mapped[str] = mapped_column(String(8))
    volume: Mapped[Decimal]
    price: Mapped[Decimal]
    commission: Mapped[Decimal]
    swap: Mapped[Decimal]
    fee: Mapped[Decimal]
    profit: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3))
    ts_utc: Mapped[datetime]
    client_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32))
    payload_hash: Mapped[str] = mapped_column(String(64), unique=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON)
    ingested_utc: Mapped[datetime] = mapped_column(default=utcnow)


class AuditLog(Base):
    """Hash-chained, append-only operator/system audit trail."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_utc: Mapped[datetime] = mapped_column(default=utcnow)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class SystemState(Base):
    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_utc: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


GENESIS_HASH = "0" * 64


def canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def audit_hash(prev: str, ts: datetime, actor: str, action: str, detail: dict[str, Any]) -> str:
    body = canonical({"prev": prev, "ts": ts.astimezone(UTC).isoformat(), "actor": actor,
                      "action": action, "detail": detail})
    return hashlib.sha256(body.encode()).hexdigest()


def append_audit(
    s: Session, actor: str, action: str, detail: dict[str, Any], ts: datetime | None = None
) -> AuditLog:
    last = s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
    prev = last.hash if last else GENESIS_HASH
    ts = ts or utcnow()
    row = AuditLog(ts_utc=ts, actor=actor, action=action, detail=detail, prev_hash=prev,
                   hash=audit_hash(prev, ts, actor, action, detail))
    s.add(row)
    s.flush()
    return row


def verify_audit_chain(s: Session) -> tuple[bool, int | None]:
    prev = GENESIS_HASH
    for row in s.scalars(select(AuditLog).order_by(AuditLog.id)):
        ts = row.ts_utc if row.ts_utc.tzinfo else row.ts_utc.replace(tzinfo=UTC)
        expected = audit_hash(prev, ts, row.actor, row.action, row.detail)
        if row.prev_hash != prev or row.hash != expected:
            return False, row.id
        prev = row.hash
    return True, None


def get_state(s: Session, key: str, default: Any = None) -> Any:
    row = s.get(SystemState, key)
    return default if row is None else row.value


def set_state(s: Session, key: str, value: Any) -> None:
    row = s.get(SystemState, key)
    if row is None:
        s.add(SystemState(key=key, value=value))
    else:
        row.value = value
    s.flush()


def make_engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
