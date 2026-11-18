"""Hard risk limits for the XAUUSD scalper.

These values are read-only to the agent. Changing them is a code change that
the account owner must approve; nothing at runtime may modify them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

INSTRUMENT = "XAU_USD"
OUNCES_PER_LOT = 100


@dataclass(frozen=True)
class RiskLimits:
    account_size_usd: float = 5000.0
    lot_size: float = 0.04
    max_daily_loss_pct: float = 2.0
    max_drawdown_pct: float = 15.0
    # Assumption pending owner approval: 0.5% per trade ("moderate").
    max_risk_per_trade_pct: float = 0.5
    max_consecutive_losses: int = 4
    max_trades_per_day: int = 20
    max_open_positions: int = 1
    # Assumption until replaced by measured session medians from OANDA pricing.
    max_spread_usd: float = 0.60
    min_stop_to_spread_ratio: float = 3.0
    stale_quote_seconds: float = 5.0
    max_consecutive_api_errors: int = 3
    news_blackout_minutes: int = 15

    @property
    def units(self) -> int:
        return round(self.lot_size * OUNCES_PER_LOT)

    @property
    def max_daily_loss_usd(self) -> float:
        return self.account_size_usd * self.max_daily_loss_pct / 100

    @property
    def max_risk_per_trade_usd(self) -> float:
        return self.account_size_usd * self.max_risk_per_trade_pct / 100


LIMITS = RiskLimits()


@dataclass(frozen=True)
class OandaConfig:
    token: str
    account_id: str
    # Practice only. Going live requires an approved code change, not an env var.
    rest_url: str = "https://api-fxpractice.oanda.com"


def oanda_config_from_env() -> OandaConfig:
    token = os.environ.get("OANDA_API_TOKEN", "")
    account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
    if not token or not account_id:
        raise RuntimeError("OANDA_API_TOKEN and OANDA_ACCOUNT_ID must be set")
    return OandaConfig(token=token, account_id=account_id)
