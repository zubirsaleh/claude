from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from sqlalchemy.engine import make_url
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TSCH_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://tsch:tsch@localhost:5432/tsch"
    # When set, the password in database_url is replaced by this file's content (Docker secret).
    database_password_file: Path | None = None
    # Phase 1 interim auth: a single operator bearer token read from a file (never from Git).
    # Phase 2 replaces this with durable user auth + MFA.
    operator_token_file: Path | None = None
    operator_token: str | None = Field(default=None, repr=False)
    approval_ttl_seconds: int = Field(default=120, ge=10, le=900)
    display_timezone: str = "Asia/Kuala_Lumpur"
    default_mode: str = "SIM"

    risk_max_risk_pct: Decimal = Decimal("0.5")
    risk_max_daily_loss_pct: Decimal = Decimal("2")
    risk_max_drawdown_pct: Decimal = Decimal("5")
    risk_max_open_positions: int = 3
    risk_max_volume: Decimal = Decimal("1")
    risk_max_spread_points: int = 50
    risk_max_quote_age_s: int = 10

    def model_post_init(self, __context: object) -> None:
        if self.database_password_file is not None:
            url = make_url(self.database_url).set(
                password=self.database_password_file.read_text().strip())
            object.__setattr__(self, "database_url", url.render_as_string(hide_password=False))

    def resolved_operator_token(self) -> str | None:
        if self.operator_token_file is not None:
            token = self.operator_token_file.read_text().strip()
            return token or None
        return self.operator_token or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
