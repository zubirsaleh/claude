"""Manual-execution desk: risk-approved signals become Telegram alerts that the owner
executes by hand in TradingView Paper Trading.

The bot cannot see the Paper Trading account, so it keeps a shadow ledger from the
owner's /taken, /skip and /closed replies plus stop/target hits seen on 1M bars.
Every alert passes the same RiskEngine gate as automated orders would.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from scalper.journal import Journal
from scalper.risk import Decision, MarketSnapshot, OrderRequest, RiskEngine

ALERT_TTL = timedelta(minutes=2)
# Assumption: TradingView OANDA:XAUUSD bars carry no spread; replace with measured values.
ASSUMED_SPREAD_USD = 0.35
MAX_BAR_AGE = timedelta(seconds=90)


@dataclass
class Trade:
    id: int
    side: str
    units: int
    entry: float
    stop: float
    take_profit: float | None
    status: str  # ALERTED, OPEN, CLOSED, SKIPPED, EXPIRED
    alerted_at: str
    fill: float | None = None
    exit: float | None = None
    pnl: float | None = None
    closed_at: str | None = None
    close_reason: str | None = None

    @property
    def sign(self) -> int:
        return 1 if self.side == "BUY" else -1


class DeskError(ValueError):
    pass


class ManualDesk:
    def __init__(self, state_path: Path, risk: RiskEngine, journal: Journal) -> None:
        self.state_path = Path(state_path)
        self.risk = risk
        self.journal = journal
        self.trades: dict[int, Trade] = {}
        self.realized = 0.0
        self.last_price: float | None = None
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text())
            self.trades = {t["id"]: Trade(**t) for t in data["trades"]}
            self.realized = data["realized"]
            self.last_price = data.get("last_price")

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.state_path.parent)
        with os.fdopen(fd, "w") as f:
            json.dump({"trades": [asdict(t) for t in self.trades.values()],
                       "realized": self.realized, "last_price": self.last_price}, f)
        os.replace(tmp, self.state_path)

    def _get(self, trade_id: int, status: str) -> Trade:
        t = self.trades.get(trade_id)
        if t is None:
            raise DeskError(f"no trade #{trade_id}")
        if t.status != status:
            raise DeskError(f"trade #{trade_id} is {t.status}, expected {status}")
        return t

    def equity(self) -> float:
        unrealized = 0.0
        if self.last_price is not None:
            for t in self.trades.values():
                if t.status == "OPEN":
                    unrealized += (self.last_price - t.fill) * t.units * t.sign
        return self.risk.limits.account_size_usd + self.realized + unrealized

    def _active(self) -> int:
        return sum(t.status in ("ALERTED", "OPEN") for t in self.trades.values())

    def propose(self, order: OrderRequest, last_close: float, bar_close_time: datetime,
                now: datetime, news_events: list[datetime] | None = None
                ) -> tuple[Decision, Trade | None]:
        self.expire(now)
        # Closed 1M bars are always older than the tick-level stale limit; a bar within
        # MAX_BAR_AGE counts as fresh, anything older is passed through and rejected.
        quote_time = now if now - bar_close_time <= MAX_BAR_AGE else bar_close_time
        mkt = MarketSnapshot(
            bid=last_close, ask=last_close + ASSUMED_SPREAD_USD, quote_time=quote_time,
            equity=self.equity(), open_positions=self._active(), news_events=news_events or [],
        )
        decision = self.risk.check_order(order, mkt, now)
        self.journal.log("risk_check", order=order, market=mkt, decision=decision)
        if not decision.allowed:
            return decision, None
        entry = mkt.ask if order.side == "BUY" else mkt.bid
        trade = Trade(
            id=max(self.trades, default=0) + 1, side=order.side, units=order.units,
            entry=entry, stop=order.stop_price, take_profit=order.take_profit_price,
            status="ALERTED", alerted_at=now.isoformat(),
        )
        self.trades[trade.id] = trade
        self.risk.record_order_placed()
        self._save()
        self.journal.log("alert_sent", trade=trade)
        return decision, trade

    def taken(self, trade_id: int, now: datetime, fill: float | None = None) -> Trade:
        self.expire(now)
        t = self._get(trade_id, "ALERTED")
        t.fill = t.entry if fill is None else fill
        if (t.fill - t.stop) * t.sign <= 0:
            raise DeskError("fill is already beyond the stop; do not take this trade")
        t.status = "OPEN"
        self._save()
        self.journal.log("trade_taken", trade=t, slippage=(t.fill - t.entry) * t.sign)
        return t

    def skip(self, trade_id: int) -> Trade:
        t = self._get(trade_id, "ALERTED")
        t.status = "SKIPPED"
        self._save()
        self.journal.log("trade_skipped", trade=t)
        return t

    def close(self, trade_id: int, exit_price: float, now: datetime, reason: str = "manual") -> Trade:
        t = self._get(trade_id, "OPEN")
        t.exit = exit_price
        t.pnl = round((exit_price - t.fill) * t.units * t.sign, 2)
        t.status, t.closed_at, t.close_reason = "CLOSED", now.isoformat(), reason
        self.realized += t.pnl
        self.risk.record_trade_closed(t.pnl, now)
        self.risk.update_equity(self.equity(), now)
        self._save()
        self.journal.log("trade_closed", trade=t)
        return t

    def expire(self, now: datetime) -> list[Trade]:
        expired = []
        for t in self.trades.values():
            if t.status == "ALERTED" and now - datetime.fromisoformat(t.alerted_at) > ALERT_TTL:
                t.status = "EXPIRED"
                expired.append(t)
        if expired:
            self._save()
        return expired

    def on_bar(self, high: float, low: float, close: float, now: datetime) -> list[Trade]:
        """Mark open trades closed when a closed 1M bar touches stop or target.

        If both are touched in one bar the stop is assumed (worst case).
        """
        self.last_price = close
        hits = []
        for t in list(self.trades.values()):
            if t.status != "OPEN":
                continue
            stop_hit = low <= t.stop if t.side == "BUY" else high >= t.stop
            tp = t.take_profit
            tp_hit = tp is not None and (high >= tp if t.side == "BUY" else low <= tp)
            if stop_hit:
                hits.append(self.close(t.id, t.stop, now, reason="stop (bar touch)"))
            elif tp_hit:
                hits.append(self.close(t.id, tp, now, reason="target (bar touch)"))
        self.expire(now)
        self.risk.update_equity(self.equity(), now)
        self._save()
        return hits

    def kill(self, reason: str) -> list[Trade]:
        self.risk.trip_kill_switch(reason)
        for t in self.trades.values():
            if t.status == "ALERTED":
                t.status = "EXPIRED"
        self._save()
        self.journal.log("kill_switch", reason=reason)
        return [t for t in self.trades.values() if t.status == "OPEN"]


def format_alert(t: Trade, lot_size: float) -> str:
    risk = abs(t.entry - t.stop) * t.units
    tp = f"{t.take_profit:.2f}" if t.take_profit is not None else "none"
    valid = (datetime.fromisoformat(t.alerted_at) + ALERT_TTL).strftime("%H:%M:%S UTC")
    return (
        f"XAUUSD {t.side} {lot_size} lot  #{t.id}\n"
        f"Entry ~{t.entry:.2f}  SL {t.stop:.2f}  TP {tp}\n"
        f"Risk ~${risk:.0f}  Valid until {valid}\n"
        f"Set SL/TP in TradingView, then reply /taken {t.id} [fill] or /skip {t.id}"
    )


def format_status(desk: ManualDesk) -> str:
    st, lim = desk.risk.state, desk.risk.limits
    day_pnl = desk.equity() - st.day_start_equity
    lines = [
        f"Equity ${desk.equity():,.2f}  (day {day_pnl:+.2f} / limit -{lim.max_daily_loss_usd:.0f})",
        f"Peak ${st.peak_equity:,.2f}  Trades today {st.trades_today}  "
        f"Loss streak {st.consecutive_losses}",
        f"Kill switch: {'ON - ' + st.kill_reason if st.kill_switch else 'off'}",
    ]
    for t in desk.trades.values():
        if t.status in ("ALERTED", "OPEN"):
            px = t.fill if t.fill is not None else t.entry
            lines.append(f"#{t.id} {t.status} {t.side} @ {px:.2f} SL {t.stop:.2f}")
    return "\n".join(lines)
