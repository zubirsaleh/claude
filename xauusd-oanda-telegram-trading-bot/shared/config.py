"""Central configuration loaded from environment variables.

Every service imports from here so that defaults and safety rules are
defined in exactly one place. Nothing in this module fabricates data;
it only reads configuration and validates it.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# --- Instrument (this project is XAU/USD only) -----------------------------
OANDA_INSTRUMENT: str = os.getenv("OANDA_INSTRUMENT", "XAU_USD")
TRADINGVIEW_SYMBOL: str = "OANDA:XAUUSD"

# --- Telegram --------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# --- OANDA -----------------------------------------------------------------
OANDA_API_KEY: str = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID: str = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENV: str = os.getenv("OANDA_ENV", "practice").strip().lower()

# --- OpenAI (optional) -----------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# --- Analysis defaults -----------------------------------------------------
DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "M15")
DEFAULT_CANDLE_COUNT: int = int(os.getenv("DEFAULT_CANDLE_COUNT", "150"))
DEFAULT_RISK_PERCENT: float = float(os.getenv("DEFAULT_RISK_PERCENT", "1.0"))
DEFAULT_ACCOUNT_BALANCE: float = float(os.getenv("DEFAULT_ACCOUNT_BALANCE", "10000"))

# --- Safety controls -------------------------------------------------------
ALLOW_LIVE_TRADING: bool = os.getenv("ALLOW_LIVE_TRADING", "false").strip().lower() == "true"
ADVISORY_ONLY: bool = os.getenv("ADVISORY_ONLY", "true").strip().lower() != "false"

# --- Service URLs (used inside docker-compose network) ---------------------
OANDA_SERVICE_URL: str = os.getenv("OANDA_SERVICE_URL", "http://oanda-service:8001")
ANALYSIS_SERVICE_URL: str = os.getenv("ANALYSIS_SERVICE_URL", "http://analysis-service:8000")

# --- Supported timeframes --------------------------------------------------
SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("M1", "M5", "M15", "M30", "H1", "H4", "D")


def oanda_base_url() -> str:
    """Return the correct OANDA REST base URL for the configured environment.

    The live endpoint is only ever returned when every safety control has
    been explicitly relaxed. Otherwise we always fall back to practice.
    """
    live_requested = OANDA_ENV == "live"
    live_allowed = ALLOW_LIVE_TRADING and not ADVISORY_ONLY and live_requested
    if live_allowed:
        return "https://api-fxtrade.oanda.com"
    return "https://api-fxpractice.oanda.com"


def using_live() -> bool:
    """True only when the live OANDA endpoint is actually in use."""
    return oanda_base_url() == "https://api-fxtrade.oanda.com"


def validate_telegram() -> None:
    """Raise a clear startup error if the Telegram token is missing."""
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Create a bot with @BotFather and "
            "put the token in your .env file before starting the bot."
        )


def validate_oanda() -> None:
    """Raise a clear startup error if OANDA credentials are missing."""
    missing = [
        name
        for name, value in (
            ("OANDA_API_KEY", OANDA_API_KEY),
            ("OANDA_ACCOUNT_ID", OANDA_ACCOUNT_ID),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing OANDA configuration: "
            + ", ".join(missing)
            + ". Generate an API token from your OANDA account and set these "
            "in your .env file."
        )
