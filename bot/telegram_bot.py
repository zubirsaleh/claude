"""Telegram bot that routes user messages through Claude with TradingView tools."""
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS
from bot.claude_handler import chat, clear_history

logger = logging.getLogger(__name__)


def _is_allowed(user_id: int) -> bool:
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_allowed(user.id):
        await update.message.reply_text("Access denied.")
        return
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your TradingView analyst powered by Claude.\n\n"
        "Ask me anything about a market, chart, or position. Examples:\n"
        "• *What's the BTC setup on the 4h?*\n"
        "• *Check ETH/USDT on Binance — 1h — any patterns?*\n"
        "• *Give me a full read on AAPL daily*\n"
        "• *EURUSD — long or short?*\n\n"
        "Use /clear to reset our conversation.",
        parse_mode="Markdown",
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return
    clear_history(update.effective_user.id)
    await update.message.reply_text("Conversation cleared.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "*Available commands*\n"
        "/start — welcome message\n"
        "/clear — reset conversation history\n"
        "/help — this message\n\n"
        "*What you can ask*\n"
        "• Full market analysis: _BTC 4h full read_\n"
        "• Candlestick patterns: _Any patterns on ETH 1h?_\n"
        "• Indicators: _RSI and MACD on AAPL daily_\n"
        "• Position ideas: _Should I long EURUSD now?_\n"
        "• Specific exchanges: _SOLUSDT on Bybit 15m_",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_allowed(user.id):
        await update.message.reply_text("Access denied.")
        return

    text = update.message.text or ""
    if not text.strip():
        return

    # Show typing indicator while Claude thinks
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    try:
        reply = await _run_in_thread(chat, user.id, text)
    except Exception as exc:
        logger.exception("Claude error for user %d", user.id)
        reply = f"Error fetching analysis: {exc}"

    # Telegram message limit is 4096 chars; split if needed
    for chunk in _split(reply, 4096):
        await update.message.reply_text(chunk, parse_mode="Markdown")


async def _run_in_thread(fn, *args):
    import asyncio, concurrent.futures
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, fn, *args)


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
