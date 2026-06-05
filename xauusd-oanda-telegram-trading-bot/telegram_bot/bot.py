"""Telegram front-end for the XAU/USD OANDA analysis bot.

Receives commands and free-text queries, forwards a parsed request to the
analysis service, and returns the formatted report. This is XAU/USD only —
any other instrument is politely refused.
"""
from __future__ import annotations

import re

import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from shared import config
from shared.logging_config import setup_logging

log = setup_logging("telegram-bot")

_TIMEOUT = 60
_ONLY_XAUUSD = "This bot is configured for XAU/USD only."

# Other instruments we explicitly recognise so we can refuse them.
# Matches concatenated/spaced/slashed FX pairs (eurusd, usd jpy, gbp/usd) plus
# common crypto, index, metal and equity tickers.
_FX_PAIR = re.compile(
    r"\b(eur|gbp|aud|nzd|cad|chf|jpy|usd)[ /]?(usd|jpy|eur|gbp|aud|nzd|cad|chf)\b",
    re.IGNORECASE,
)
_OTHER_SYMBOLS = re.compile(
    r"\b(btc|eth|bitcoin|ethereum|nas100|us30|spx|sp500|dax|"
    r"silver|xag|oil|wti|brent|nvda|aapl|tsla|amzn|msft)\b",
    re.IGNORECASE,
)
_GOLD = re.compile(r"\b(gold|xau ?usd|xauusd|xau)\b", re.IGNORECASE)
_TF = re.compile(r"\b(M1|M5|M15|M30|H1|H4|D)\b", re.IGNORECASE)


# --------------------------------------------------------------------------
# Analysis-service calls
# --------------------------------------------------------------------------
def _post_analyze(payload: dict) -> str:
    url = f"{config.ANALYSIS_SERVICE_URL}/analyze"
    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        log.error("analysis-service unreachable: %s", exc)
        return "Analysis service is unavailable. Please try again shortly."
    if resp.status_code >= 400:
        try:
            return resp.json().get("detail", "Analysis failed.")
        except Exception:
            return f"Analysis failed (HTTP {resp.status_code})."
    return resp.json().get("text", "No analysis returned.")


def _service_online(base: str, path: str = "/health") -> bool:
    try:
        r = requests.get(f"{base}{path}", timeout=10)
        return r.status_code < 400
    except requests.RequestException:
        return False


# --------------------------------------------------------------------------
# Command handlers
# --------------------------------------------------------------------------
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    msg = (
        "👋 *XAU/USD OANDA Trading Assistant*\n\n"
        "I analyse gold (XAU/USD) using live OANDA data, technical indicators, "
        "candlestick patterns and a rule-based signal engine.\n\n"
        "*Examples:*\n"
        "• /analyze — full M15 analysis\n"
        "• /analyze H1 — analysis on a chosen timeframe\n"
        "• /scalp — M5 setup confirmed by M15\n"
        "• /daily — H4 + Daily bias\n"
        "• /price — latest bid/ask\n"
        "• /risk — sample position sizing\n\n"
        "You can also just type: _gold now_, _xauusd m15_, _scalp gold_.\n\n"
        "_This is analysis only, not financial advice._"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def help_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    msg = (
        "*Commands*\n"
        "/start — welcome & examples\n"
        "/help — this message\n"
        "/clear — clear your session context\n"
        "/status — check bot, analysis & OANDA services\n"
        "/price — latest XAU/USD bid/ask\n"
        "/analyze [TF] — full analysis (default M15)\n"
        "/scalp — M5 + M15 scalping setup\n"
        "/daily — H4 + Daily higher-timeframe bias\n"
        "/risk — sample position sizing\n\n"
        "Timeframes: M1, M5, M15, M30, H1, H4, D"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text("Session context cleared. ✅")


async def status(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    analysis_ok = _service_online(config.ANALYSIS_SERVICE_URL)
    oanda_ok = _service_online(config.OANDA_SERVICE_URL)
    env = "live" if config.using_live() else "practice"
    msg = (
        "*System Status*\n"
        "• Telegram bot: 🟢 online\n"
        f"• Analysis service: {'🟢 online' if analysis_ok else '🔴 offline'}\n"
        f"• OANDA service: {'🟢 online' if oanda_ok else '🔴 offline'}\n"
        f"• OANDA environment: {env}\n"
        f"• Advisory only: {'ON' if config.ADVISORY_ONLY else 'OFF'}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def price(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, _post_analyze({"mode": "price"}))


async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tf = _extract_tf(" ".join(context.args)) if context.args else None
    if context.args and tf is None:
        await update.message.reply_text(
            "Unsupported timeframe. Use M1, M5, M15, M30, H1, H4, or D."
        )
        return
    await _reply(update, _post_analyze({"mode": "analyze", "timeframe": tf}))


async def scalp(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, _post_analyze({"mode": "scalp"}))


async def daily(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, _post_analyze({"mode": "daily"}))


async def risk(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, _post_analyze({"mode": "risk"}))


# --------------------------------------------------------------------------
# Free-text handler
# --------------------------------------------------------------------------
async def text_handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    lower = text.lower()

    mentions_other = bool(_OTHER_SYMBOLS.search(lower) or _FX_PAIR.search(lower))
    mentions_gold = bool(_GOLD.search(lower))
    if mentions_other and not mentions_gold:
        await update.message.reply_text(_ONLY_XAUUSD)
        return

    tf = _extract_tf(text)

    if "scalp" in lower:
        await _reply(update, _post_analyze({"mode": "scalp"}))
        return
    if any(w in lower for w in ("daily", "h4", "higher timeframe", "swing")):
        if tf in ("H4", "D"):
            await _reply(update, _post_analyze({"mode": "analyze", "timeframe": tf}))
        else:
            await _reply(update, _post_analyze({"mode": "daily"}))
        return
    if "price" in lower or lower in ("gold", "gold now", "xauusd"):
        if any(w in lower for w in ("read", "analy", "buy", "sell", "long", "short", "m1", "m5", "m15", "m30", "h1")):
            await _reply(update, _post_analyze({"mode": "analyze", "timeframe": tf}))
        else:
            await _reply(update, _post_analyze({"mode": "price"}))
        return

    # Anything else gold-related → full analysis.
    await _reply(update, _post_analyze({"mode": "analyze", "timeframe": tf}))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _extract_tf(text: str) -> str | None:
    m = _TF.search(text or "")
    return m.group(1).upper() if m else None


async def _reply(update: Update, text: str) -> None:
    # Telegram hard-limits messages to 4096 chars.
    for chunk in _split(text):
        await update.message.reply_text(chunk)


def _split(text: str, limit: int = 4000):
    while text:
        yield text[:limit]
        text = text[limit:]


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main() -> None:
    config.validate_telegram()
    log.info("Starting Telegram bot for %s", config.OANDA_INSTRUMENT)

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("analyze", analyze_cmd))
    app.add_handler(CommandHandler("scalp", scalp))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("risk", risk))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
