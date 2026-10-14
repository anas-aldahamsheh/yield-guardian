"""Alembic migrations, run from the command line (`alembic upgrade head`) or at API startup."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

API_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = API_ROOT / "alembic.ini"

# Tables another library creates in the same database: LangGraph's AsyncPostgresSaver.setup()
# makes and migrates its checkpoint tables itself. Autogenerate must neither drop nor diff them.
EXTERNAL_TABLES = frozenset(
    {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}
)


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """Alembic ``include_name`` hook: leave out the external tables (and their indexes)."""
    if type_ == "table":
        return name not in EXTERNAL_TABLES
    if type_ == "index" and isinstance(parent_names, dict):
        return parent_names.get("table_name") not in EXTERNAL_TABLES
    return True


# Held while migrating, so several API processes starting together migrate once.
MIGRATION_LOCK_KEY = 0x59475F4D49475241  # "YG_MIGRA"


def alembic_config(url: str | None = None) -> Config:
    """The project's Alembic configuration; `url` overrides DATABASE_URL."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    if url is not None:
        config.attributes["url"] = url
    return config


def _upgrade(connection: Connection, revision: str) -> None:
    config = alembic_config()
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


async def upgrade(engine: AsyncEngine, revision: str = "head") -> None:
    """Upgrade the database under an advisory lock, in one transaction."""
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
        )
        await connection.run_sync(_upgrade, revision)
