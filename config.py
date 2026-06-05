import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_IDS: list[int] = [
    int(uid.strip())
    for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip()
]
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
TV_USERNAME: str = os.getenv("TRADINGVIEW_USERNAME", "")
TV_PASSWORD: str = os.getenv("TRADINGVIEW_PASSWORD", "")
MAX_HISTORY: int = int(os.getenv("MAX_HISTORY", "20"))
