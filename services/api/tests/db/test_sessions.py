"""Sessions: guests, admin login, expiry, logout. No attempt limits exist (PLAN D-009)."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from tests.db.conftest import ADMIN_PASSWORD, ADMIN_USERNAME
from yield_guardian.contracts.services import NotReadyError
from yield_guardian.contracts.session import GuestSessionCreate, LoginRequest
from yield_guardian.core.settings import Settings
from yield_guardian.db.tables import SessionRow
from yield_guardian.services.errors import AuthenticationError
from yield_guardian.services.persistence import Persistence
from yield_guardian.services.protocols import VISITOR, SessionManager
from yield_guardian.services.sessions import LOGIN_FAILED, DbSessionManager


def _login(username: str, password: str) -> LoginRequest:
    return LoginRequest(username=username, password=SecretStr(password))


async def test_no_or_unknown_token_is_a_visitor(persistence: Persistence) -> None:
    sessions: SessionManager = persistence.sessions
    assert await sessions.resolve(None) is VISITOR
    assert await sessions.resolve("") is VISITOR
    assert await sessions.resolve("unknown-token") is VISITOR
    assert await sessions.resolve("x" * 10_000) is VISITOR


async def test_guest_session_is_an_engineer_and_stores_only_the_token_hash(
    persistence: Persistence,
) -> None:
    before = datetime.now(UTC)
    session, token = await persistence.sessions.guest(
        GuestSessionCreate(display_name="Dana"), client="127.0.0.1"
    )
    assert session.role == "engineer"
    assert session.display_name == "Dana"
    assert session.csrf_token is not None
    assert len(session.csrf_token) >= 40
    assert len(token) >= 43
    assert session.expires_at is not None
    assert (
        before + timedelta(minutes=29)
        < session.expires_at
        <= datetime.now(UTC) + timedelta(minutes=30)
    )
    assert await persistence.sessions.resolve(token) == session

    async with persistence.database.sessionmaker() as db:
        row = (await db.scalars(select(SessionRow))).one()
    assert row.token_hash == hashlib.sha256(token.encode()).digest()
    assert token not in (row.csrf_token, str(row.session_id), row.client)

    audit = await persistence.audit.list(action="session.guest")
    assert [e.actor_name for e in audit.items] == ["Dana"]


async def test_each_session_gets_its_own_tokens(persistence: Persistence) -> None:
    first, token_a = await persistence.sessions.guest(GuestSessionCreate(), client="a")
    second, token_b = await persistence.sessions.guest(GuestSessionCreate(), client="b")
    assert token_a != token_b
    assert first.csrf_token != second.csrf_token
    assert first.display_name is None


async def test_expired_session_is_a_visitor(persistence: Persistence) -> None:
    _, token = await persistence.sessions.guest(GuestSessionCreate(), client="c")
    async with persistence.database.sessionmaker() as db, db.begin():
        await db.execute(
            update(SessionRow).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await persistence.sessions.resolve(token) is VISITOR


async def test_admin_login(persistence: Persistence) -> None:
    session, token = await persistence.sessions.login(
        _login(ADMIN_USERNAME, ADMIN_PASSWORD), client="127.0.0.1"
    )
    assert session.role == "admin"
    assert session.display_name == ADMIN_USERNAME
    assert (await persistence.sessions.resolve(token)).role == "admin"


@pytest.mark.parametrize(
    ("username", "password"),
    [(ADMIN_USERNAME, "wrong password"), ("someone", ADMIN_PASSWORD), ("someone", "wrong")],
)
async def test_failed_login_has_one_generic_message(
    persistence: Persistence, username: str, password: str
) -> None:
    with pytest.raises(AuthenticationError) as caught:
        await persistence.sessions.login(_login(username, password), client="127.0.0.1")
    assert caught.value.detail == LOGIN_FAILED
    assert caught.value.problem().status == 401
    entries = (await persistence.audit.list(action="session.login_failed")).items
    assert len(entries) == 1
    assert entries[0].actor_role == "visitor"
    assert username not in entries[0].model_dump_json()


async def test_failed_logins_never_lock_the_account(persistence: Persistence) -> None:
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            await persistence.sessions.login(_login(ADMIN_USERNAME, "nope"), client="x")
    session, _ = await persistence.sessions.login(
        _login(ADMIN_USERNAME, ADMIN_PASSWORD), client="x"
    )
    assert session.role == "admin"


async def test_login_without_an_admin_account_is_not_ready(
    persistence: Persistence, db_settings: Settings
) -> None:
    settings = db_settings.model_copy(update={"admin_username": None, "admin_password_hash": None})
    sessions = DbSessionManager(persistence.database.sessionmaker, settings)
    with pytest.raises(NotReadyError):
        await sessions.login(_login(ADMIN_USERNAME, ADMIN_PASSWORD), client="x")


def test_a_malformed_admin_hash_fails_at_startup(db_settings: Settings) -> None:
    settings = db_settings.model_copy(update={"admin_password_hash": SecretStr("plain-text")})
    with pytest.raises(ValueError):
        DbSessionManager(None, settings)  # type: ignore[arg-type]


async def test_logout_ends_the_session(persistence: Persistence) -> None:
    session, token = await persistence.sessions.guest(GuestSessionCreate(), client="c")
    await persistence.sessions.logout(session)
    assert await persistence.sessions.resolve(token) is VISITOR
    assert (await persistence.audit.list(action="session.logout")).total == 1
    await persistence.sessions.logout(session)
    assert (await persistence.audit.list(action="session.logout")).total == 1
