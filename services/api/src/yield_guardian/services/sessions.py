"""Device sessions and their workspaces: visitors, "Try as engineer", the admin login, handoff codes
to continue on another device, and the admin's list of active sessions.

Every browser gets a visitor session on its first visit; the session owns a workspace, where the
runs, uploads and investigations it starts are recorded. The cookie carries
`secrets.token_urlsafe(32)` and the database keeps only its SHA-256. A new token is issued
whenever the role or the workspace changes (so a token planted before a sign-in is worthless
after it); the CSRF token stays the same for the life of the session, so other open tabs keep
working.

Lifetimes: a device session ends `workspace_session_days` after its last use (each use moves it
forward, at most every five minutes); the engineer or admin role ends `session_ttl_minutes` after
it was taken, and the session goes on as a visitor in the same workspace. Signing out does the
same at once. A handoff code is single use and ends after `handoff_minutes`; only its SHA-256 is
stored. A workspace lives `workspace_session_days` (30) after it was last used, by any of its
devices: then :meth:`DbSessionManager.prune` deletes it, and its runs, uploads, investigations,
work orders and audit entries with it. A workspace no device can reach any more (its last session
ended, was revoked or started afresh, and no live code joins it) is deleted at the next prune.

There are no attempt limits or lockouts (PLAN D-009); the admin password is protected by scrypt
and its length, and a handoff code by its 60 random bits and its short life.
"""

import asyncio
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

import structlog
from sqlalchemy import delete, exists, func, or_, select, text, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.contracts.services import InvalidArgumentError, NotFoundError, NotReadyError
from yield_guardian.contracts.session import GuestSessionCreate, LoginRequest, SessionRole
from yield_guardian.contracts.workorders import AuditAction
from yield_guardian.contracts.workspace import (
    AdminSession,
    AdminSessionPage,
    HandoffCreated,
    WorkspaceDevice,
    WorkspaceSummary,
)
from yield_guardian.core.settings import Settings
from yield_guardian.db.tables import (
    AuditEntryRow,
    HandoffRow,
    InvestigationRow,
    RunRow,
    SessionRow,
    UploadRow,
    WorkspaceRow,
)
from yield_guardian.services import audit, cursors
from yield_guardian.services.errors import AuthenticationError
from yield_guardian.services.passwords import PasswordHash
from yield_guardian.services.protocols import VISITOR, ActiveSession
from yield_guardian.services.runs import GoneError

log = structlog.get_logger(__name__)

MAX_TOKEN_LENGTH = 128
LOGIN_FAILED = "The username or password is incorrect."
TOUCH_EVERY = timedelta(minutes=5)
HANDOFF_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base 32: no I, L, O or U
HANDOFF_LENGTH = 12
_LOOKALIKES = str.maketrans({"I": "1", "L": "1", "O": "0"})
CURSOR_KIND = "ses"
NOT_A_CODE = "That is not a handoff code: a code has 12 letters and digits, like 7K2M-QX9D-4HRT."
NO_SUCH_CODE = "No device made this code. Check it, or make a new one on the other device."
CODE_USED = "This code has already been used. Make a new one on the other device."
SAME_WORKSPACE = (
    "This device is already in that workspace: open the code on the device you want to bring in."
)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def normalise_code(code: str) -> str | None:
    """The 12 characters of a handoff code as typed (any case, dashes and spaces, I, L and O
    read as 1, 1 and 0), or None when it cannot be one."""
    raw = code.upper().replace("-", "").replace(" ", "").translate(_LOOKALIKES)
    if len(raw) != HANDOFF_LENGTH or any(c not in HANDOFF_ALPHABET for c in raw):
        return None
    return raw


def shown_code(raw: str) -> str:
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def _role_ended(row: SessionRow, now: datetime) -> bool:
    return row.role != "visitor" and (row.role_expires_at is None or row.role_expires_at <= now)


def _active(row: SessionRow) -> ActiveSession:
    return ActiveSession(
        session_id=str(row.session_id),
        role=cast(SessionRole, row.role),
        display_name=row.display_name,
        csrf_token=row.csrf_token,
        expires_at=row.role_expires_at if row.role != "visitor" else None,
        workspace_id=str(row.workspace_id) if row.workspace_id is not None else None,
        session_expires_at=row.expires_at,
    )


def _uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class SessionPruneReport:
    sessions: int
    handoffs: int
    workspaces: int
    investigations: int = 0


CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")
"""LangGraph's tables in the same database (``db.migrate.EXTERNAL_TABLES``): an investigation's
paused state, keyed by its ID as the thread ID."""


async def forget_checkpoints(db: AsyncSession, investigation_ids: list[str]) -> None:
    """Delete the investigator's saved state of these investigations, where the checkpointer
    created its tables in this database."""
    if not investigation_ids:
        return
    for table in CHECKPOINT_TABLES:
        if await db.scalar(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": table}):
            await db.execute(
                text(f"DELETE FROM {table} WHERE thread_id = ANY(:ids)"),  # noqa: S608 - fixed names
                {"ids": investigation_ids},
            )


class DbSessionManager:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessionmaker = sessionmaker
        self._ttl = timedelta(minutes=settings.session_ttl_minutes)
        self._session_life = timedelta(days=settings.workspace_session_days)
        self._handoff_life = timedelta(minutes=settings.handoff_minutes)
        self._admin_username = settings.admin_username
        hashed = settings.admin_password_hash
        self._admin_hash = PasswordHash.parse(hashed.get_secret_value()) if hashed else None

    # Resolving --------------------------------------------------------------------------------

    async def resolve(self, token: str | None) -> ActiveSession:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return VISITOR
        digest = token_hash(token)
        now = datetime.now(UTC)
        async with self._sessionmaker() as db:
            row = await db.scalar(
                select(SessionRow).where(
                    SessionRow.token_hash == digest, SessionRow.expires_at > now
                )
            )
            if row is None or not hmac.compare_digest(row.token_hash, digest):
                return VISITOR
            ended = _role_ended(row, now)
            if ended or row.last_seen_at is None or row.last_seen_at <= now - TOUCH_EVERY:
                await self._touch(db, row, now, end_role=ended)
                await db.commit()
        return _active(row)

    async def _touch(
        self, db: AsyncSession, row: SessionRow, now: datetime, *, end_role: bool = False
    ) -> None:
        values: dict[str, object] = {"last_seen_at": now, "expires_at": now + self._session_life}
        if end_role:
            values.update(role="visitor", display_name=None, role_expires_at=None)
        await db.execute(
            update(SessionRow).where(SessionRow.session_id == row.session_id).values(**values)
        )
        if row.workspace_id is not None:
            await db.execute(
                update(WorkspaceRow)
                .where(WorkspaceRow.workspace_id == row.workspace_id)
                .values(last_seen_at=now)
            )
        for name, value in values.items():
            setattr(row, name, value)

    # Opening and changing roles ---------------------------------------------------------------

    async def open_visitor(self, *, client: str) -> tuple[ActiveSession, str]:
        """A new visitor session with its own new workspace (a browser's first visit)."""
        async with self._sessionmaker() as db, db.begin():
            row, token = await self._new(db, "visitor", None, client)
        return _active(row), token

    async def guest(
        self, body: GuestSessionCreate, *, client: str, current: ActiveSession = VISITOR
    ) -> tuple[ActiveSession, str]:
        return await self._raise(current, "engineer", body.display_name, client, "session.guest")

    async def login(
        self, body: LoginRequest, *, client: str, current: ActiveSession = VISITOR
    ) -> tuple[ActiveSession, str]:
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
        return await self._raise(current, "admin", self._admin_username, client, "session.login")

    async def logout(self, session: ActiveSession) -> tuple[ActiveSession, str] | None:
        """Back to visitor in the same workspace, with a new token; None when the session is
        unknown or already a visitor."""
        session_id = _uuid(session.session_id)
        if session_id is None:
            return None
        now = datetime.now(UTC)
        async with self._sessionmaker() as db, db.begin():
            row = await self._lock(db, session_id)
            if row is None or row.role == "visitor":
                return None
            actor = audit.Actor.of(_active(row))
            row.role, row.display_name, row.role_expires_at = "visitor", None, None
            token = self._rotate(row, now)
            audit.record(db, actor, "session.logout", "session", str(session_id))
        return _active(row), token

    async def _raise(
        self,
        current: ActiveSession,
        role: SessionRole,
        display_name: str | None,
        client: str,
        action: AuditAction,
    ) -> tuple[ActiveSession, str]:
        """Give the current session `role` (keeping its workspace) with a new token, or open a
        new session with a new workspace when there is none."""
        now = datetime.now(UTC)
        session_id = _uuid(current.session_id)
        async with self._sessionmaker() as db, db.begin():
            row = await self._lock(db, session_id) if session_id is not None else None
            token: str
            if row is None:
                row, token = await self._new(db, role, display_name, client)
            else:
                row.role, row.display_name = role, display_name
                row.role_expires_at = now + self._ttl
                token = self._rotate(row, now)
            session = _active(row)
            audit.record(db, audit.Actor.of(session), action, "session", session.session_id)
        return session, token

    async def _new(
        self,
        db: AsyncSession,
        role: SessionRole,
        display_name: str | None,
        client: str,
        workspace_id: uuid.UUID | None = None,
    ) -> tuple[SessionRow, str]:
        now = datetime.now(UTC)
        if workspace_id is None:
            workspace_id = uuid.uuid4()
            db.add(WorkspaceRow(workspace_id=workspace_id, created_at=now, last_seen_at=now))
            await db.flush()
        token = secrets.token_urlsafe(32)
        row = SessionRow(
            session_id=uuid.uuid4(),
            token_hash=token_hash(token),
            role=role,
            display_name=display_name,
            csrf_token=secrets.token_urlsafe(32),
            client=client,
            created_at=now,
            expires_at=now + self._session_life,
            workspace_id=workspace_id,
            last_seen_at=now,
            role_expires_at=now + self._ttl if role != "visitor" else None,
        )
        db.add(row)
        await db.flush()
        return row, token

    def _rotate(self, row: SessionRow, now: datetime) -> str:
        token = secrets.token_urlsafe(32)
        row.token_hash = token_hash(token)
        row.last_seen_at = now
        row.expires_at = now + self._session_life
        return token

    @staticmethod
    async def _lock(db: AsyncSession, session_id: uuid.UUID) -> SessionRow | None:
        return await db.scalar(
            select(SessionRow)
            .where(SessionRow.session_id == session_id, SessionRow.expires_at > func.now())
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def _own(self, db: AsyncSession, session: ActiveSession) -> SessionRow:
        session_id = _uuid(session.session_id)
        row = await self._lock(db, session_id) if session_id is not None else None
        if row is None or row.workspace_id is None:
            raise NotFoundError("This device has no workspace yet. Reload the page.")
        return row

    # The workspace ----------------------------------------------------------------------------

    async def workspace(self, session: ActiveSession) -> WorkspaceSummary:
        workspace_id = _uuid(session.workspace_id)
        now = datetime.now(UTC)
        async with self._sessionmaker() as db:
            found = await db.get(WorkspaceRow, workspace_id) if workspace_id is not None else None
            if found is None:
                raise NotFoundError("This device has no workspace yet. Reload the page.")
            devices = (
                await db.scalars(
                    select(SessionRow)
                    .where(
                        SessionRow.workspace_id == found.workspace_id, SessionRow.expires_at > now
                    )
                    .order_by(SessionRow.last_seen_at.desc().nulls_last(), SessionRow.session_id)
                )
            ).all()
            counts = [
                await db.scalar(
                    select(func.count())
                    .select_from(table)
                    .where(table.workspace_id == workspace_id)
                )
                or 0
                for table in (RunRow, UploadRow, InvestigationRow)
            ]
        return WorkspaceSummary(
            workspace_id=str(found.workspace_id),
            created_at=found.created_at,
            devices=[
                WorkspaceDevice(
                    current=str(d.session_id) == session.session_id,
                    role="visitor" if _role_ended(d, now) else cast(SessionRole, d.role),
                    created_at=d.created_at,
                    last_seen_at=d.last_seen_at or d.created_at,
                    expires_at=d.expires_at,
                )
                for d in devices
            ],
            runs=counts[0],
            uploads=counts[1],
            investigations=counts[2],
            session_days=self._session_life.days,
            handoff_minutes=int(self._handoff_life.total_seconds() // 60),
        )

    async def create_handoff(self, session: ActiveSession) -> HandoffCreated:
        """A code that attaches one more device to this workspace; it replaces any unused code
        this workspace made before. The code itself is never stored or logged."""
        now = datetime.now(UTC)
        raw = "".join(secrets.choice(HANDOFF_ALPHABET) for _ in range(HANDOFF_LENGTH))
        async with self._sessionmaker() as db, db.begin():
            row = await self._own(db, session)
            await db.execute(
                delete(HandoffRow).where(
                    HandoffRow.workspace_id == row.workspace_id, HandoffRow.used_at.is_(None)
                )
            )
            expires = now + self._handoff_life
            db.add(
                HandoffRow(
                    code_hash=token_hash(raw),
                    workspace_id=row.workspace_id,
                    created_by=row.session_id,
                    created_at=now,
                    expires_at=expires,
                    used_at=None,
                )
            )
            audit.record(
                db,
                audit.Actor.of(session),
                "workspace.handoff_created",
                "workspace",
                str(row.workspace_id),
                {"expires_at": expires.isoformat()},
            )
        code = shown_code(raw)
        return HandoffCreated(code=code, expires_at=expires, join_path=f"/join#code={code}")

    async def join(self, session: ActiveSession, code: str) -> tuple[ActiveSession, str]:
        """Attach this device to the workspace that made `code` (once; the code is then used).
        The device keeps its own role and gets a new token. What the device made before comes
        with it when no other device shares its old workspace (nothing it made is lost); a
        workspace another device still uses keeps its own."""
        raw = normalise_code(code)
        if raw is None:
            raise InvalidArgumentError(NOT_A_CODE)
        now = datetime.now(UTC)
        async with self._sessionmaker() as db, db.begin():
            handoff = await db.scalar(
                select(HandoffRow).where(HandoffRow.code_hash == token_hash(raw)).with_for_update()
            )
            if handoff is None:
                raise NotFoundError(NO_SUCH_CODE)
            if handoff.used_at is not None:
                raise GoneError(CODE_USED)
            if handoff.expires_at <= now:
                raise GoneError(
                    f"This code ended at {handoff.expires_at:%H:%M} UTC: codes last "
                    f"{int(self._handoff_life.total_seconds() // 60)} minutes. Make a new one on "
                    "the other device."
                )
            row = await self._own(db, session)
            if row.workspace_id == handoff.workspace_id:
                raise InvalidArgumentError(SAME_WORKSPACE)
            handoff.used_at = now
            await self._bring_along(db, row, handoff.workspace_id, now)
            row.workspace_id = handoff.workspace_id
            token = self._rotate(row, now)
            await db.execute(
                update(WorkspaceRow)
                .where(WorkspaceRow.workspace_id == handoff.workspace_id)
                .values(last_seen_at=now)
            )
            audit.record(
                db,
                audit.Actor.of(_active(row)),
                "workspace.joined",
                "workspace",
                str(handoff.workspace_id),
            )
        return _active(row), token

    @staticmethod
    async def _bring_along(
        db: AsyncSession, row: SessionRow, target: uuid.UUID, now: datetime
    ) -> None:
        """Move the runs, uploads, investigations and audit entries of `row`'s workspace into
        `target` when no other live session shares that workspace."""
        old = row.workspace_id
        if old is None:
            return
        shared = await db.scalar(
            select(func.count())
            .select_from(SessionRow)
            .where(
                SessionRow.workspace_id == old,
                SessionRow.session_id != row.session_id,
                SessionRow.expires_at > now,
            )
        )
        if shared:
            return
        for table in (RunRow, UploadRow, InvestigationRow, AuditEntryRow):
            await db.execute(
                update(table).where(table.workspace_id == old).values(workspace_id=target)
            )

    async def fresh(self, session: ActiveSession) -> tuple[ActiveSession, str]:
        """Move this device to a new, empty workspace. Other devices keep the old one."""
        now = datetime.now(UTC)
        async with self._sessionmaker() as db, db.begin():
            row = await self._own(db, session)
            workspace_id = uuid.uuid4()
            db.add(WorkspaceRow(workspace_id=workspace_id, created_at=now, last_seen_at=now))
            await db.flush()
            row.workspace_id = workspace_id
            token = self._rotate(row, now)
            audit.record(
                db, audit.Actor.of(_active(row)), "workspace.fresh", "workspace", str(workspace_id)
            )
        return _active(row), token

    # Admin ------------------------------------------------------------------------------------

    async def list_sessions(
        self, *, current: ActiveSession, cursor: str | None = None, limit: int = 50
    ) -> AdminSessionPage:
        """Active sessions, most recently seen first, with what their workspace holds."""
        now = datetime.now(UTC)
        seen = func.coalesce(SessionRow.last_seen_at, SessionRow.created_at)
        active = SessionRow.expires_at > now
        query = select(SessionRow).where(active)
        if cursor:
            at, session_id = cursors.decode(CURSOR_KIND, cursor, str, str)
            try:
                position = (datetime.fromisoformat(str(at)), uuid.UUID(str(session_id)))
            except ValueError as error:
                raise InvalidArgumentError("The cursor is not valid.") from error
            query = query.where(tuple_(seen, SessionRow.session_id) < tuple_(*position))
        async with self._sessionmaker() as db:
            rows = (
                await db.scalars(
                    query.order_by(seen.desc(), SessionRow.session_id.desc()).limit(limit + 1)
                )
            ).all()
            total = await db.scalar(select(func.count()).select_from(SessionRow).where(active))
            workspaces = await db.scalar(
                select(func.count(func.distinct(SessionRow.workspace_id))).where(active)
            )
            page = list(rows[:limit])
            ids = {r.workspace_id for r in page if r.workspace_id is not None}
            counts: dict[str, dict[uuid.UUID, int]] = {}
            for name, table in (
                ("devices", SessionRow),
                ("runs", RunRow),
                ("uploads", UploadRow),
                ("investigations", InvestigationRow),
            ):
                found = select(table.workspace_id, func.count()).where(table.workspace_id.in_(ids))
                if table is SessionRow:
                    found = found.where(active)
                grouped = (await db.execute(found.group_by(table.workspace_id))).all()
                counts[name] = {w: n for w, n in grouped if w is not None}
        items = [
            AdminSession(
                session_id=str(r.session_id),
                role="visitor" if _role_ended(r, now) else cast(SessionRole, r.role),
                display_name=None if _role_ended(r, now) else r.display_name,
                created_at=r.created_at,
                last_seen_at=r.last_seen_at or r.created_at,
                expires_at=r.expires_at,
                role_expires_at=None if _role_ended(r, now) else r.role_expires_at,
                workspace_id=str(r.workspace_id) if r.workspace_id is not None else None,
                **{
                    name: counts[name].get(r.workspace_id, 0) if r.workspace_id else 0
                    for name in ("devices", "runs", "uploads", "investigations")
                },
                current=str(r.session_id) == current.session_id,
            )
            for r in page
        ]
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = cursors.encode(
                CURSOR_KIND,
                (last.last_seen_at or last.created_at).isoformat(),
                str(last.session_id),
            )
        return AdminSessionPage(
            items=items, next_cursor=next_cursor, total=total or 0, workspaces=workspaces or 0
        )

    async def revoke(self, session_id: str, *, by: ActiveSession) -> None:
        """End a device session at once: that device starts again with a new, empty workspace
        on its next visit. Its workspace stays while another device uses it; with none, the next
        prune deletes it with everything in it."""
        target = _uuid(session_id)
        if target is None:
            raise NotFoundError(f"Session {session_id} does not exist.")
        async with self._sessionmaker() as db, db.begin():
            deleted = await db.execute(
                delete(SessionRow)
                .where(SessionRow.session_id == target)
                .returning(SessionRow.session_id)
            )
            if deleted.first() is None:
                raise NotFoundError(f"Session {session_id} does not exist or has ended.")
            audit.record(db, audit.Actor.of(by), "session.revoked", "session", str(target))

    # Expiry -----------------------------------------------------------------------------------

    async def prune(self) -> SessionPruneReport:
        """Delete ended sessions, used or ended handoff codes, and every workspace that was last
        used `workspace_session_days` ago or that no device can reach any more (no session is
        attached to it and no live code joins it). A workspace takes its runs, uploads,
        investigations (with their work orders and investigator checkpoints) and audit entries
        with it."""
        now = datetime.now(UTC)
        async with self._sessionmaker() as db, db.begin():
            sessions = await db.execute(
                delete(SessionRow)
                .where(SessionRow.expires_at <= now)
                .returning(SessionRow.session_id)
            )
            handoffs = await db.execute(
                delete(HandoffRow)
                .where(or_(HandoffRow.expires_at <= now, HandoffRow.used_at.is_not(None)))
                .returning(HandoffRow.code_hash)
            )
            attached = exists().where(SessionRow.workspace_id == WorkspaceRow.workspace_id)
            joinable = exists().where(HandoffRow.workspace_id == WorkspaceRow.workspace_id)
            ended = select(WorkspaceRow.workspace_id).where(
                or_(WorkspaceRow.last_seen_at <= now - self._session_life, ~attached & ~joinable)
            )
            doomed = list((await db.scalars(ended.with_for_update(skip_locked=True))).all())
            investigations: list[str] = []
            if doomed:
                investigations = list(
                    (
                        await db.scalars(
                            select(InvestigationRow.investigation_id).where(
                                InvestigationRow.workspace_id.in_(doomed)
                            )
                        )
                    ).all()
                )
                await db.execute(delete(WorkspaceRow).where(WorkspaceRow.workspace_id.in_(doomed)))
                await forget_checkpoints(db, investigations)
            report = SessionPruneReport(
                sessions=len(sessions.all()),
                handoffs=len(handoffs.all()),
                workspaces=len(doomed),
                investigations=len(investigations),
            )
        if report.sessions or report.handoffs or report.workspaces:
            log.info(
                "sessions_pruned",
                sessions=report.sessions,
                handoffs=report.handoffs,
                workspaces=report.workspaces,
                investigations=report.investigations,
            )
        return report
