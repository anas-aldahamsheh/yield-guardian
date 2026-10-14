"""Alembic environment: async engine from DATABASE_URL, or a connection handed in by the API."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from yield_guardian.core.settings import Settings
from yield_guardian.db import tables  # noqa: F401  (registers the tables on Base.metadata)
from yield_guardian.db.base import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = config.attributes.get("url")
    if isinstance(url, str):
        return url
    configured = Settings().database_url
    if configured is None:
        raise RuntimeError("Set DATABASE_URL to run migrations.")
    return configured.get_secret_value()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_server_default=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


def run_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if isinstance(connection, Connection):
    _run(connection)
elif context.is_offline_mode():
    run_offline()
else:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    asyncio.run(_run_async())
