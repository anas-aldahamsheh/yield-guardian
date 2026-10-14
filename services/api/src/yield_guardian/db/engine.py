"""The async engine (SQLAlchemy 2.1 with asyncpg) and its lifetime as a registry Resource."""

from collections.abc import Callable

import structlog
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from yield_guardian.db import migrate

log = structlog.get_logger(__name__)


def create_engine(url: str) -> AsyncEngine:
    """An engine whose connections run in UTC."""
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args={"server_settings": {"timezone": "UTC", "application_name": "yield-guardian"}},
    )


def asyncpg_dsn(url: str) -> str:
    """The plain libpq DSN asyncpg accepts, from a SQLAlchemy URL."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


class Database:
    """Owns the engine. Starting it migrates to head (when asked) and checks the connection;
    `on_status` hears whether the database is usable."""

    def __init__(self, url: str, *, migrate_on_start: bool = True) -> None:
        self.dsn = asyncpg_dsn(url)
        self.engine = create_engine(url)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)
        self._migrate_on_start = migrate_on_start
        self.on_status: Callable[[bool], None] | None = None

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            log.warning("database_unreachable", exc_info=True)
            return False
        return True

    async def start(self) -> None:
        if self._migrate_on_start:
            await migrate.upgrade(self.engine)
            log.info("database_migrated")
        ok = await self.ping()
        if self.on_status is not None:
            self.on_status(ok)

    async def stop(self) -> None:
        if self.on_status is not None:
            self.on_status(False)
        await self.engine.dispose()
