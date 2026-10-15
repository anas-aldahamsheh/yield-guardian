"""Migrations upgrade, downgrade and upgrade again cleanly, and match the table definitions."""

import asyncio

import asyncpg
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from tests.db.conftest import temporary_database
from yield_guardian.db import tables  # noqa: F401
from yield_guardian.db.base import Base
from yield_guardian.db.engine import Database, asyncpg_dsn
from yield_guardian.db.migrate import alembic_config, include_name

OWN_TABLES = {
    "alarm_states",
    "audit_entries",
    "investigation_events",
    "investigation_jobs",
    "investigations",
    "sessions",
    "work_orders",
    "llm_calls",
    "llm_response_cache",
    "llm_role_assignments",
    "chat_routes",
    "llm_evaluations",
    "knowledge_chunks",
    "runs",
    "run_items",
    "run_unit_charts",
    "run_stages",
    "run_events",
    "uploads",
}


async def _schema(url: str) -> tuple[set[str], bool]:
    connection = await asyncpg.connect(asyncpg_dsn(url))
    try:
        rows = await connection.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        vector = await connection.fetchval(
            "SELECT count(*) FROM pg_extension WHERE extname = 'vector'"
        )
    finally:
        await connection.close()
    return {r["tablename"] for r in rows} - {"alembic_version"}, vector == 1


def test_upgrade_downgrade_upgrade() -> None:
    with temporary_database(migrate=False) as url:
        config = alembic_config(url)
        command.upgrade(config, "head")
        assert asyncio.run(_schema(url)) == (OWN_TABLES, True)
        command.downgrade(config, "base")
        assert asyncio.run(_schema(url))[0] == set()
        command.upgrade(config, "head")
        assert asyncio.run(_schema(url)) == (OWN_TABLES, True)


def _diff(connection: Connection) -> list[object]:
    context = MigrationContext.configure(connection, opts={"include_name": include_name})
    return list(compare_metadata(context, Base.metadata))


async def test_migrations_match_the_table_definitions(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert await connection.run_sync(_diff) == []
    finally:
        await engine.dispose()


def test_concurrent_startup_migrations_apply_once() -> None:
    async def start_two(url: str) -> None:
        databases = [Database(url), Database(url)]
        try:
            await asyncio.gather(*(d.start() for d in databases))
        finally:
            await asyncio.gather(*(d.stop() for d in databases))

    with temporary_database(migrate=False) as url:
        asyncio.run(start_two(url))
        assert asyncio.run(_schema(url)) == (OWN_TABLES, True)
