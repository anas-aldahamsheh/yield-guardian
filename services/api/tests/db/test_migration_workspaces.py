"""Migration 0005 (workspaces), up and down with sessions and rows already stored. Rows are
synthetic test values."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
from alembic import command

from tests.db.conftest import temporary_database
from yield_guardian.db.engine import asyncpg_dsn
from yield_guardian.db.migrate import alembic_config

SESSION = uuid.UUID("5d0c1b8e-3f7a-4e21-8c6d-9a0b1c2d3e4f")
CREATED = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
ROLE_ENDS = CREATED + timedelta(minutes=30)


async def _sql(url: str, *statements: tuple[str, tuple[object, ...]]) -> list[list[asyncpg.Record]]:
    connection = await asyncpg.connect(asyncpg_dsn(url))
    try:
        return [await connection.fetch(sql, *args) for sql, args in statements]
    finally:
        await connection.close()


def _before(url: str) -> None:
    asyncio.run(
        _sql(
            url,
            (
                "INSERT INTO sessions (session_id, token_hash, role, display_name, csrf_token, "
                "client, created_at, expires_at) VALUES ($1, $2, 'engineer', 'Mia', 'csrf', "
                "'test', $3, $4)",
                (SESSION, b"\x01" * 32, CREATED, ROLE_ENDS),
            ),
            (
                "INSERT INTO investigations (investigation_id, title, status, trigger_kind, "
                "trigger_ref, created_at, updated_at) VALUES ('inv_0000000001', 'Test', "
                "'queued', 'unit', '1062', now(), now())",
                (),
            ),
        )
    )


def test_workspaces_migrate_up_and_down_with_stored_sessions() -> None:
    with temporary_database(migrate=False) as url:
        config = alembic_config(url)
        command.upgrade(config, "0004")
        _before(url)

        command.upgrade(config, "0005")
        sessions, workspaces, investigations = asyncio.run(
            _sql(
                url,
                (
                    "SELECT workspace_id, role_expires_at, last_seen_at, expires_at FROM sessions",
                    (),
                ),
                ("SELECT workspace_id, created_at, last_seen_at FROM workspaces", ()),
                ("SELECT workspace_id FROM investigations", ()),
            )
        )
        # The session gets its own workspace and keeps its lifetime as the end of its role.
        assert [tuple(r) for r in sessions] == [(SESSION, ROLE_ENDS, CREATED, ROLE_ENDS)]
        assert [tuple(r) for r in workspaces] == [(SESSION, CREATED, CREATED)]
        assert [r["workspace_id"] for r in investigations] == [None]  # of no workspace
        asyncio.run(
            _sql(
                url,
                (
                    "INSERT INTO sessions (session_id, token_hash, role, csrf_token, client, "
                    "created_at, expires_at, workspace_id) VALUES ($1, $2, 'visitor', 'c', 't', "
                    "now(), now() + interval '30 days', $3)",
                    (uuid.uuid4(), b"\x02" * 32, SESSION),
                ),
                (
                    "UPDATE sessions SET expires_at = now() + interval '30 days' "
                    "WHERE session_id = $1",
                    (SESSION,),
                ),
            )
        )

        command.downgrade(config, "0004")
        (left,) = asyncio.run(_sql(url, ("SELECT session_id, role, expires_at FROM sessions", ())))
        # Visitors go (the earlier schema has none); a role keeps the end it had.
        assert [tuple(r) for r in left] == [(SESSION, "engineer", ROLE_ENDS)]

        command.upgrade(config, "head")
        (again,) = asyncio.run(_sql(url, ("SELECT workspace_id FROM sessions", ())))
        assert [r["workspace_id"] for r in again] == [SESSION]
