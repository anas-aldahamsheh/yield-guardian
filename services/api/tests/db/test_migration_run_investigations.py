"""Migration 0004 (PLAN_V2 3.4, 7.3): ``run_alarm`` investigations and confirmed causes, up and
down. Rows are synthetic test values."""

import asyncio

import asyncpg
import pytest
from alembic import command

from tests.db.conftest import temporary_database
from yield_guardian.db.engine import asyncpg_dsn
from yield_guardian.db.migrate import alembic_config

RUN_ALARM = ("inv_0000000001", "run_alarm", "run_testcase0001:RA-1")
UNIT = ("inv_0000000002", "unit", "1062")


async def _insert(url: str, row: tuple[str, str, str]) -> None:
    connection = await asyncpg.connect(asyncpg_dsn(url))
    try:
        await connection.execute(
            "INSERT INTO investigations (investigation_id, title, status, trigger_kind, "
            "trigger_ref, created_at, updated_at) VALUES ($1, 'Test', 'queued', $2, $3, now(), "
            "now())",
            *row,
        )
    finally:
        await connection.close()


async def _state(url: str) -> tuple[bool, list[str]]:
    """Whether work orders have ``confirmed_cause``, and the stored investigation IDs."""
    connection = await asyncpg.connect(asyncpg_dsn(url))
    try:
        column = await connection.fetchval(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'work_orders' AND column_name = 'confirmed_cause'"
        )
        rows = await connection.fetch(
            "SELECT investigation_id FROM investigations ORDER BY investigation_id"
        )
    finally:
        await connection.close()
    return column == 1, [r["investigation_id"] for r in rows]


def test_run_alarm_investigations_and_confirmed_causes_migrate_up_and_down() -> None:
    with temporary_database(migrate=False) as url:
        config = alembic_config(url)
        command.upgrade(config, "0004")
        asyncio.run(_insert(url, RUN_ALARM))
        asyncio.run(_insert(url, UNIT))
        assert asyncio.run(_state(url)) == (True, [RUN_ALARM[0], UNIT[0]])

        command.downgrade(config, "-1")
        assert asyncio.run(_state(url)) == (False, [UNIT[0]])  # the earlier schema has no runs
        with pytest.raises(asyncpg.CheckViolationError):
            asyncio.run(_insert(url, RUN_ALARM))

        command.upgrade(config, "head")
        asyncio.run(_insert(url, RUN_ALARM))
        assert asyncio.run(_state(url)) == (True, [RUN_ALARM[0], UNIT[0]])
