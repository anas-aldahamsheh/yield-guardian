"""Who may see what: every visitor is a separate user (the owner's rule of 2026-10-15).

A run, its events, its upload, the investigations started from it, their work orders and audit
entries belong to the workspace that made them. Another workspace gets exactly the answer a
missing ID gets (404, or 410 for an ID old enough to have expired), so an ID reveals nothing.
Devices joined through a handoff code are the same workspace and see everything in it.

Rows with no workspace (made before migration 0005, or by an API client without a session
cookie) are listed nowhere and stay reachable by their ID, as before. The one exception is the
product's example (:func:`is_example`): a recorded investigation, seeded at startup and made by
no visitor, is listed for every visitor apart from their own, with its work orders and audit
entries, and nobody changes it.

Stores take a :class:`Viewer` explicitly. The few reads that happen deep inside the science
services (a unit's alarm states and investigations) read the viewer of the current request or
investigation job from :func:`current_viewer`, set with :func:`viewing`; with none set they show
no workspace's activity at all.
"""

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import ColumnElement, false, or_
from sqlalchemy.orm import InstrumentedAttribute

from yield_guardian.db.tables import InvestigationRow


@dataclass(frozen=True, slots=True)
class Viewer:
    """The workspace a request (or an investigation job) acts for; None without a session."""

    workspace_id: str | None

    @property
    def uuid(self) -> UUID | None:
        try:
            return UUID(self.workspace_id) if self.workspace_id else None
        except ValueError:
            return None

    def sees(self, owner: UUID | str | None) -> bool:
        """A row owned by `owner` can be opened by its ID."""
        return owner is None or self.owns(owner)

    def owns(self, owner: UUID | str | None) -> bool:
        """A row owned by `owner` is this workspace's own (listed in its lists)."""
        return owner is not None and self.uuid is not None and str(owner) == str(self.uuid)


NOBODY = Viewer(workspace_id=None)


def visible(column: InstrumentedAttribute[UUID | None], viewer: Viewer) -> ColumnElement[bool]:
    """SQL: rows `viewer` may open by ID (its own, and rows with no workspace)."""
    workspace = viewer.uuid
    return column.is_(None) if workspace is None else or_(column.is_(None), column == workspace)


def owned(column: InstrumentedAttribute[UUID | None], viewer: Viewer) -> ColumnElement[bool]:
    """SQL: rows of `viewer`'s own workspace (what its lists show)."""
    workspace = viewer.uuid
    return false() if workspace is None else column == workspace


def is_example(recorded: bool, owner: UUID | str | None) -> bool:
    """The product's example: a recorded run (generated once on the server, seeded at startup),
    which no workspace owns. Every visitor lists it, apart from their own investigations, with
    its work orders and audit entries; it is read-only: nobody decides it or changes its work
    order, since every visitor would see the change."""
    return recorded and owner is None


def examples() -> ColumnElement[bool]:
    """SQL: the investigations that are the product's examples (:func:`is_example`)."""
    return InvestigationRow.recorded.is_(True) & InvestigationRow.workspace_id.is_(None)


_CURRENT: ContextVar[Viewer | None] = ContextVar("yield_guardian_viewer", default=None)


def current_viewer() -> Viewer | None:
    return _CURRENT.get()


@contextlib.contextmanager
def viewing(viewer: Viewer) -> Iterator[None]:
    """Reads deep in the science services act for `viewer` inside this block (also across the
    yields of a streamed answer: the task that drives the stream keeps it)."""
    token = _CURRENT.set(viewer)
    try:
        yield
    finally:
        # A stream abandoned at a yield is closed later from another context, which never had
        # this value: there is nothing to undo there.
        with contextlib.suppress(ValueError):
            _CURRENT.reset(token)
