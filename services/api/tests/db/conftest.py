"""Database fixtures. Each test session creates a temporary database from TEST_DATABASE_URL, migrates
it to head and drops it at the end; tests skip only when the variable is unset."""

import asyncio
import contextlib
import os
import secrets
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from alembic import command
from pydantic import SecretStr
from sqlalchemy import make_url

from tests.db.fakes import FakeRunner
from yield_guardian.core.settings import Settings
from yield_guardian.db.engine import asyncpg_dsn
from yield_guardian.db.migrate import alembic_config
from yield_guardian.services.passwords import hash_password
from yield_guardian.services.persistence import Persistence, build_persistence

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "correct horse battery staple, synthetic test value"

TABLES = (
    "sessions, investigations, investigation_events, investigation_jobs, work_orders, "
    "audit_entries, alarm_states"
)


async def _admin(url: str, sql: str) -> None:
    connection = await asyncpg.connect(asyncpg_dsn(url))
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


@contextlib.contextmanager
def temporary_database(*, migrate: bool) -> Iterator[str]:
    """A new empty database next to TEST_DATABASE_URL's, dropped afterwards."""
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("TEST_DATABASE_URL is not set")
    name = f"yg_test_{os.getpid()}_{secrets.token_hex(4)}"
    asyncio.run(_admin(base, f'CREATE DATABASE "{name}"'))
    url = make_url(base).set(database=name).render_as_string(hide_password=False)
    try:
        if migrate:
            command.upgrade(alembic_config(url), "head")
        yield url
    finally:
        asyncio.run(_admin(base, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with temporary_database(migrate=True) as url:
        yield url


@pytest.fixture(scope="session")
def admin_hash() -> str:
    return hash_password(ADMIN_PASSWORD)


@pytest.fixture
def db_settings(database_url: str, admin_hash: str) -> Settings:
    return Settings(
        environment="test",
        log_json=False,
        database_url=SecretStr(database_url),
        admin_username=ADMIN_USERNAME,
        admin_password_hash=SecretStr(admin_hash),
        session_ttl_minutes=30,
    )


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


async def clean(url: str) -> None:
    await _admin(
        url,
        f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE; ALTER SEQUENCE work_order_number_seq RESTART",
    )


@pytest.fixture
async def persistence(
    database_url: str, db_settings: Settings, runner: FakeRunner
) -> AsyncIterator[Persistence]:
    """Started stores on a clean database, with the fake runner."""
    await clean(database_url)
    built = build_persistence(db_settings, runner_provider=lambda: runner, migrate=False)
    for resource in built.resources:
        await resource.start()
    try:
        yield built
    finally:
        for resource in reversed(built.resources):
            await resource.stop()
