from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool
from tsch_api.config import get_settings
from tsch_api.db import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata,
                      literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.attributes.get("url") or get_settings().database_url
    engine = engine_from_config({"sqlalchemy.url": url}, prefix="sqlalchemy.",
                                poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
