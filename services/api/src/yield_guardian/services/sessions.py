"""Cookie sessions: "Try as engineer" guests and the admin login.

The cookie carries `secrets.token_urlsafe(32)`; the database keeps only its SHA-256. Each session
has its own random CSRF token and a fixed lifetime of `session_ttl_minutes`. There are no attempt
limits or lockouts (PLAN D-009); the admin password is protected by scrypt and its length.
"""

import asyncio
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.contracts.services import NotReadyError
from yield_guardian.contracts.session import GuestSessionCreate, LoginRequest, SessionRole
from yield_guardian.contracts.workorders import AuditAction
from yield_guardian.core.settings import Settings
from yield_guardian.db.tables import SessionRow
from yield_guardian.services import audit
from yield_guardian.services.errors import AuthenticationError
from yield_guardian.services.passwords import PasswordHash
from yield_guardian.services.protocols import VISITOR, ActiveSession

log = structlog.get_logger(__name__)

MAX_TOKEN_LENGTH = 128
LOGIN_FAILED = "The username or password is incorrect."


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _active(row: SessionRow) -> ActiveSession:
    return ActiveSession(
        session_id=str(row.session_id),
        role=cast(SessionRole, row.role),
        display_name=row.display_name,
        csrf_token=row.csrf_token,
        expires_at=row.expires_at,
    )


class DbSessionManager:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessionmaker = sessionmaker
        self._ttl = timedelta(minutes=settings.session_ttl_minutes)
        self._admin_username = settings.admin_username
        hashed = settings.admin_password_hash
        self._admin_hash = PasswordHash.parse(hashed.get_secret_value()) if hashed else None

    async def resolve(self, token: str | None) -> ActiveSession:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return VISITOR
        digest = token_hash(token)
        async with self._sessionmaker() as db:
            row = await db.scalar(
                select(SessionRow).where(
                    SessionRow.token_hash == digest, SessionRow.expires_at > datetime.now(UTC)
                )
            )
        if row is None or not hmac.compare_digest(row.token_hash, digest):
            return VISITOR
        return _active(row)

    async def guest(self, body: GuestSessionCreate, *, client: str) -> tuple[ActiveSession, str]:
        return await self._open("engineer", body.display_name, client, "session.guest")

    async def login(self, body: LoginRequest, *, client: str) -> tuple[ActiveSession, str]:
        if self._admin_username is None or self._admin_hash is None:
            raise NotReadyError("Admin sign-in is not configured on this server.")
        password = body.password.get_secret_value()
        password_ok = await asyncio.to_thread(self._admin_hash.verify, password)
        username_ok = hmac.compare_digest(body.username.encode(), self._admin_username.encode())
        if not (password_ok and username_ok):
            log.info("login_failed", client=client)
            async with self._sessionmaker() as db, db.begin():
                audit.record(
                    db, audit.Actor("visitor", None), "session.login_failed", "session", "-"
                )
            raise AuthenticationError(LOGIN_FAILED)
        return await self._open("admin", self._admin_username, client, "session.login")

    async def logout(self, session: ActiveSession) -> None:
        if not session.session_id:
            return
        async with self._sessionmaker() as db, db.begin():
            deleted = await db.execute(
                delete(SessionRow)
                .where(SessionRow.session_id == uuid.UUID(session.session_id))
                .returning(SessionRow.session_id)
            )
            if deleted.first() is not None:
                audit.record(
                    db, audit.Actor.of(session), "session.logout", "session", session.session_id
                )

    async def _open(
        self, role: SessionRole, display_name: str | None, client: str, action: AuditAction
    ) -> tuple[ActiveSession, str]:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        row = SessionRow(
            session_id=uuid.uuid4(),
            token_hash=token_hash(token),
            role=role,
            display_name=display_name,
            csrf_token=secrets.token_urlsafe(32),
            client=client,
            created_at=now,
            expires_at=now + self._ttl,
        )
        session = _active(row)
        async with self._sessionmaker() as db, db.begin():
            await db.execute(delete(SessionRow).where(SessionRow.expires_at <= now))
            db.add(row)
            audit.record(db, audit.Actor.of(session), action, "session", session.session_id)
        return session, token
