from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tsch_api.brokers.sim import SimBroker
from tsch_api.config import Settings
from tsch_api.db import make_engine
from tsch_api.main import create_app

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "test-operator-token-0123456789abcdef"
PG_URL = os.environ.get("TSCH_TEST_DATABASE_URL")


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 3, 10, 9, 30, tzinfo=UTC))


@pytest.fixture
def sim(clock: FakeClock) -> SimBroker:
    return SimBroker(clock=clock)


def _migrate_pg(url: str) -> Engine:
    from alembic import command
    from alembic.config import Config

    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(ROOT / "services/api/alembic.ini"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    return engine


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def backend(request: pytest.FixtureRequest) -> str:
    if request.param == "postgres" and not PG_URL:
        pytest.skip("TSCH_TEST_DATABASE_URL not set")
    return str(request.param)


@dataclass
class Harness:
    client: TestClient
    sim: SimBroker
    clock: FakeClock
    engine: Engine
    backend: str
    auth: dict[str, str]


@pytest.fixture
def harness(backend: str, sim: SimBroker, clock: FakeClock) -> Iterator[Harness]:
    if backend == "postgres":
        assert PG_URL
        engine = _migrate_pg(PG_URL)
        create_schema = False
    else:
        engine = make_engine("sqlite://")
        create_schema = True
    settings = Settings(database_url="unused://", operator_token=TOKEN, approval_ttl_seconds=60)
    app = create_app(settings, engine=engine, sim=sim, clock=clock, create_schema=create_schema)
    with TestClient(app) as client:
        yield Harness(client, sim, clock, engine, backend, {"Authorization": f"Bearer {TOKEN}"})
    engine.dispose()
