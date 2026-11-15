"""Deterministic in-process simulated broker.

All prices are SYNTHETIC: a seeded random walk, not market data. Never present SIM output as
broker or market results.

Fault injection (`inject_next_submit`) reproduces the cases the order pipeline must survive:
  "timeout_filled"     broker filled the order but the response was lost
  "timeout_not_placed" request lost before the broker saw it
  "reject"             broker rejects the order
"""

from __future__ import annotations

import hashlib
import random
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from tsch_contracts import (
    AccountMode,
    AccountState,
    AccountType,
    ApprovedOrder,
    Bar,
    BrokerIdentity,
    BrokerOrder,
    BrokerReceipt,
    BrokerTimeout,
    DataSource,
    Fill,
    HealthStatus,
    Position,
    Quote,
    ReceiptStatus,
    ReconciliationReport,
    Side,
    SymbolSpecs,
    Timeframe,
)
from tsch_contracts.models import TIMEFRAME_SECONDS

Fault = Literal["timeout_filled", "timeout_not_placed", "reject"]

SIM_SPECS: dict[str, SymbolSpecs] = {
    "XAUUSD": SymbolSpecs(
        symbol="XAUUSD", digits=2, point=Decimal("0.01"), tick_size=Decimal("0.01"),
        tick_value=Decimal("1.00"), contract_size=Decimal("100"), volume_min=Decimal("0.01"),
        volume_max=Decimal("50"), volume_step=Decimal("0.01"), stop_level_points=0,
        freeze_level_points=0, currency_profit="USD", currency_margin="USD",
    ),
    "EURUSD": SymbolSpecs(
        symbol="EURUSD", digits=5, point=Decimal("0.00001"), tick_size=Decimal("0.00001"),
        tick_value=Decimal("1.00"), contract_size=Decimal("100000"),
        volume_min=Decimal("0.01"), volume_max=Decimal("50"), volume_step=Decimal("0.01"),
        stop_level_points=0, freeze_level_points=0, currency_profit="USD",
        currency_margin="EUR",
    ),
}
_BASE_PRICE = {"XAUUSD": Decimal("2400.00"), "EURUSD": Decimal("1.08000")}
_SPREAD_POINTS = {"XAUUSD": 20, "EURUSD": 10}
_VOL_PER_MIN = {"XAUUSD": 0.0006, "EURUSD": 0.0002}
COMMISSION_PER_LOT_PER_SIDE = Decimal("-3.50")

SIM_IDENTITY = BrokerIdentity(
    broker="TSCH-SIM", server="SIM-LOCAL", login="SIM000001", account_type=AccountType.DEMO,
    mode=AccountMode.SIM, currency="USD", trade_allowed=True,
)
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@lru_cache(maxsize=64)
def _day_path(symbol: str, day: int) -> tuple[Decimal, ...]:
    """Deterministic 1440 one-minute mid prices for a SIM day. Each day is anchored
    independently so any minute is computable without replaying history."""
    spec = SIM_SPECS[symbol]
    seed = int.from_bytes(hashlib.sha256(f"{symbol}:{day}".encode()).digest()[:8])
    rng = random.Random(seed)  # noqa: S311 — synthetic prices, not security
    level = float(_BASE_PRICE[symbol]) * (1 + rng.uniform(-0.05, 0.05))
    out = []
    for _ in range(1440):
        level *= 1 + rng.gauss(0, _VOL_PER_MIN[symbol])
        out.append(Decimal(str(level)).quantize(spec.point))
    return tuple(out)


def _minute_mid(symbol: str, minute_index: int) -> Decimal:
    return _day_path(symbol, minute_index // 1440)[minute_index % 1440]


class SimBroker:
    def __init__(
        self,
        clock: Callable[[], datetime] = _utcnow,
        starting_balance: Decimal = Decimal("10000.00"),
    ) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._balance = starting_balance
        self._positions: dict[str, Position] = {}
        self._fills: list[Fill] = []
        self._receipts: dict[str, BrokerReceipt] = {}
        self._seq = 0
        self.connected = True
        self.heartbeat_frozen_at: datetime | None = None
        self.inject_next_submit: Fault | None = None
        self.identity = SIM_IDENTITY

    # --- read side -------------------------------------------------------------------
    def get_identity(self) -> BrokerIdentity:
        return self.identity

    def get_health(self) -> HealthStatus:
        hb = self.heartbeat_frozen_at or self._clock()
        return HealthStatus(
            connected=self.connected,
            last_heartbeat_utc=hb if self.connected else self.heartbeat_frozen_at,
            detail="SIM adapter (synthetic prices)",
        )

    def get_symbol_specs(self, symbol: str) -> SymbolSpecs:
        return SIM_SPECS[symbol]

    def get_quote(self, symbol: str) -> Quote:
        now = self._clock()
        mid = _minute_mid(symbol, int((now - _EPOCH).total_seconds() // 60))
        spec = SIM_SPECS[symbol]
        half = spec.point * _SPREAD_POINTS[symbol] / 2
        return Quote(
            symbol=symbol,
            bid=(mid - half).quantize(spec.point),
            ask=(mid + half).quantize(spec.point),
            ts_utc=now,
        )

    def get_candles(
        self, symbol: str, timeframe: Timeframe, start_utc: datetime, end_utc: datetime
    ) -> list[Bar]:
        step = TIMEFRAME_SECONDS[timeframe] // 60
        first = int((start_utc - _EPOCH).total_seconds() // 60)
        first -= first % step
        last = int((end_utc - _EPOCH).total_seconds() // 60)
        if last - first > 1440 * 7:
            raise ValueError("SIM candle range limited to 7 days")
        bars: list[Bar] = []
        for m in range(first, last, step):
            prices = [_minute_mid(symbol, i) for i in range(m, m + step)]
            bars.append(Bar(
                symbol=symbol, timeframe=timeframe,
                ts_utc=_EPOCH + timedelta(minutes=m),
                open=prices[0], high=max(prices), low=min(prices), close=prices[-1],
                tick_volume=step * 10, source=DataSource.SIMULATED,
            ))
        return bars

    def _unrealized(self, p: Position) -> Decimal:
        spec = SIM_SPECS[p.symbol]
        q = self.get_quote(p.symbol)
        exit_px = q.bid if p.side == Side.BUY else q.ask
        direction = 1 if p.side == Side.BUY else -1
        return (exit_px - p.price_open) * direction / spec.tick_size * spec.tick_value * p.volume

    def get_account_state(self) -> AccountState:
        with self._lock:
            upl = sum((self._unrealized(p) for p in self._positions.values()), Decimal(0))
            equity = self._balance + upl
            return AccountState(
                balance=self._balance, equity=equity.quantize(Decimal("0.01")),
                margin=Decimal(0), free_margin=equity.quantize(Decimal("0.01")),
                currency="USD", ts_utc=self._clock(),
            )

    def get_positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    def get_open_orders(self) -> list[BrokerOrder]:
        return []  # SIM fills market orders immediately

    def get_fills(self, cursor: int = 0) -> tuple[list[Fill], int]:
        with self._lock:
            return self._fills[cursor:], len(self._fills)

    def find_by_client_id(self, idempotency_key: str) -> BrokerReceipt | None:
        with self._lock:
            return self._receipts.get(idempotency_key)

    def reconcile(self) -> ReconciliationReport:
        with self._lock:
            return ReconciliationReport(
                ts_utc=self._clock(), positions=list(self._positions.values()),
                open_orders=[], fills_seen=len(self._fills),
                receipts_by_client_id=dict(self._receipts),
            )

    # --- write side ------------------------------------------------------------------
    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq:08d}"

    def _reject(self, key: str, msg: str) -> BrokerReceipt:
        r = BrokerReceipt(status=ReceiptStatus.REJECTED, idempotency_key=key, message=msg)
        self._receipts[key] = r
        return r

    def submit_approved_demo_order(self, order: ApprovedOrder) -> BrokerReceipt:
        key = order.idempotency_key
        with self._lock:
            if key in self._receipts:
                return self._receipts[key]
            if not self.connected:
                raise BrokerTimeout("SIM disconnected")
            fault, self.inject_next_submit = self.inject_next_submit, None
            if fault == "timeout_not_placed":
                raise BrokerTimeout("SIM injected timeout before placement")
            if fault == "reject":
                return self._reject(key, "SIM injected rejection")
            now = self._clock()
            if now > order.expires_utc:
                return self._reject(key, "approval expired")
            if not order.identity.same_account(self.identity):
                return self._reject(key, "account identity mismatch")
            p = order.proposal
            if p.account_mode != AccountMode.SIM:
                return self._reject(key, f"SIM cannot execute mode {p.account_mode}")
            if p.symbol not in SIM_SPECS:
                return self._reject(key, f"unknown symbol {p.symbol}")

            q = self.get_quote(p.symbol)
            price = q.ask if p.side == Side.BUY else q.bid
            order_id, deal_id, pos_id = (
                self._next_id("O"), self._next_id("D"), self._next_id("P"))
            self._positions[pos_id] = Position(
                position_id=pos_id, symbol=p.symbol, side=p.side, volume=p.volume,
                price_open=price, sl=p.sl, tp=p.tp, opened_utc=now, client_id=key,
            )
            commission = COMMISSION_PER_LOT_PER_SIDE * p.volume
            self._balance += commission
            self._fills.append(Fill(
                deal_id=deal_id, order_id=order_id, position_id=pos_id, symbol=p.symbol,
                side=p.side, entry="IN", volume=p.volume, price=price, commission=commission,
                swap=Decimal(0), fee=Decimal(0), profit=Decimal(0), currency="USD",
                ts_utc=now, client_id=key, source=DataSource.SIMULATED,
            ))
            receipt = BrokerReceipt(
                status=ReceiptStatus.ACKED, idempotency_key=key, broker_order_id=order_id,
                deal_id=deal_id, position_id=pos_id, fill_price=price, message="filled",
            )
            self._receipts[key] = receipt
            if fault == "timeout_filled":
                raise BrokerTimeout("SIM injected timeout after fill")
            return receipt

    def close_demo_position(self, position_id: str, idempotency_key: str) -> BrokerReceipt:
        with self._lock:
            if idempotency_key in self._receipts:
                return self._receipts[idempotency_key]
            pos = self._positions.get(position_id)
            if pos is None:
                return self._reject(idempotency_key, f"no open position {position_id}")
            q = self.get_quote(pos.symbol)
            spec = SIM_SPECS[pos.symbol]
            exit_side = Side.SELL if pos.side == Side.BUY else Side.BUY
            price = q.bid if pos.side == Side.BUY else q.ask
            direction = 1 if pos.side == Side.BUY else -1
            profit = ((price - pos.price_open) * direction / spec.tick_size
                      * spec.tick_value * pos.volume).quantize(Decimal("0.01"))
            commission = COMMISSION_PER_LOT_PER_SIDE * pos.volume
            self._balance += profit + commission
            order_id, deal_id = self._next_id("O"), self._next_id("D")
            self._fills.append(Fill(
                deal_id=deal_id, order_id=order_id, position_id=position_id,
                symbol=pos.symbol, side=exit_side, entry="OUT", volume=pos.volume,
                price=price, commission=commission, swap=Decimal(0), fee=Decimal(0),
                profit=profit, currency="USD", ts_utc=self._clock(),
                client_id=idempotency_key, source=DataSource.SIMULATED,
            ))
            del self._positions[position_id]
            receipt = BrokerReceipt(
                status=ReceiptStatus.ACKED, idempotency_key=idempotency_key,
                broker_order_id=order_id, deal_id=deal_id, position_id=position_id,
                fill_price=price, message="closed",
            )
            self._receipts[idempotency_key] = receipt
            return receipt
