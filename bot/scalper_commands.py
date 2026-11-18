"""Telegram commands for the XAUUSD manual-execution desk (TradingView Paper Trading).

Trading commands require TELEGRAM_ALLOWED_USERS to be set; an empty allowlist denies them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import ALLOWED_USER_IDS
from scalper.journal import Journal
from scalper.manual_desk import DeskError, ManualDesk, format_status
from scalper.risk import RiskEngine

logger = logging.getLogger(__name__)

STATE_DIR = Path("state")
_desk: ManualDesk | None = None


def get_desk() -> ManualDesk:
    global _desk
    if _desk is None:
        _desk = ManualDesk(STATE_DIR / "desk.json", RiskEngine(STATE_DIR / "risk.json"),
                           Journal(STATE_DIR / "journal.jsonl"))
    return _desk


def _authorized(update: Update) -> bool:
    return bool(ALLOWED_USER_IDS) and update.effective_user.id in ALLOWED_USER_IDS


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _guarded(update: Update, fn) -> None:
    if not _authorized(update):
        await update.message.reply_text("Access denied.")
        return
    try:
        await update.message.reply_text(fn())
    except (DeskError, ValueError, IndexError) as exc:
        await update.message.reply_text(f"Not done: {exc}")


async def cmd_taken(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    def run():
        args = context.args
        fill = float(args[1]) if len(args) > 1 else None
        t = get_desk().taken(int(args[0]), _now(), fill)
        return f"#{t.id} OPEN {t.side} @ {t.fill:.2f}  SL {t.stop:.2f}"
    await _guarded(update, run)


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _guarded(update, lambda: f"#{get_desk().skip(int(context.args[0])).id} skipped")


async def cmd_closed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    def run():
        t = get_desk().close(int(context.args[0]), float(context.args[1]), _now())
        return f"#{t.id} CLOSED @ {t.exit:.2f}  P&L {t.pnl:+.2f}\n\n{format_status(get_desk())}"
    await _guarded(update, run)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _guarded(update, lambda: format_status(get_desk()))


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    def run():
        still_open = get_desk().kill("owner /kill")
        ids = ", ".join(f"#{t.id}" for t in still_open) or "none"
        return ("KILL SWITCH ON. No new alerts.\n"
                f"CLOSE ALL XAUUSD POSITIONS IN TRADINGVIEW NOW. Open in ledger: {ids}\n"
                "Report each with /closed <id> <price>. /resume to restart.")
    await _guarded(update, run)


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    def run():
        get_desk().risk.reset_kill_switch()
        get_desk().journal.log("kill_switch_reset", by=update.effective_user.id)
        return "Kill switch reset.\n\n" + format_status(get_desk())
    await _guarded(update, run)


async def monitor_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Each minute: feed the latest closed 1M bar to the desk and report stop/target hits."""
    from scalper.data import normalize_tv_bars
    from trading.fetcher import get_ohlcv

    desk = get_desk()
    try:
        raw = get_ohlcv("XAUUSD", "OANDA", "1m", 5)
        bars = normalize_tv_bars(raw, _local_tz())
        if bars.empty:
            return
        bar = bars.iloc[-1]
        hits = desk.on_bar(bar["high"], bar["low"], bar["close"], _now())
        desk.risk.record_api_ok()
    except Exception as exc:
        logger.exception("monitor_job failed")
        desk.risk.record_api_error()
        if desk.risk.state.kill_switch:
            await _broadcast(context, f"Data feed failing ({exc}). Kill switch ON. Check TradingView.")
        return
    for t in hits:
        await _broadcast(context, f"#{t.id} {t.close_reason} @ {t.exit:.2f}  P&L {t.pnl:+.2f}\n"
                                  "Confirm in TradingView; correct with /closed if different.")


def _local_tz() -> str:
    from tzlocal import get_localzone_name
    return get_localzone_name()


async def _broadcast(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    for uid in ALLOWED_USER_IDS:
        await context.bot.send_message(chat_id=uid, text=text)


def register(app: Application) -> None:
    app.add_handler(CommandHandler("taken", cmd_taken))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("closed", cmd_closed))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("resume", cmd_resume))
    if app.job_queue is not None:
        app.job_queue.run_repeating(monitor_job, interval=60, first=5)
    else:
        logger.warning("job-queue extra not installed: stop/target monitoring disabled")
