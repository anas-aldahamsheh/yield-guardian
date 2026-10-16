"""Sessions and workspaces. Everything is viewable without one; actions need "Try as engineer" or
an admin login.

Every browser gets a session on its first visit (no sign-up): a visitor session that owns a
**workspace**, where the runs, uploads and investigations it starts are recorded. Another device
joins the same workspace with a short-lived, single-use handoff code. "Try as engineer" and the
admin login raise the role of the same session, so the workspace is kept; signing out lowers it
back to visitor and keeps the workspace too.

The session lives in an HttpOnly, SameSite=Lax cookie. Unsafe requests carry `csrf_token` in the
X-CSRF-Token header.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, SecretStr, StringConstraints

from yield_guardian.contracts.base import Contract

SessionRole = Literal["visitor", "engineer", "admin"]

WorkspaceId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    Field(
        description="A workspace: the runs, uploads and investigations of the devices attached "
        "to it. Knowing it grants nothing; only a session cookie or a handoff code does.",
        examples=["0b8f3c1e-6a52-4c47-9d0e-2f8a1b7c4d55"],
    ),
]


class WorkspaceInfo(Contract):
    workspace_id: WorkspaceId
    session_expires_at: datetime = Field(
        description="When this device's session ends if the device is not used again; each "
        "visit moves it forward (30 days by default)."
    )


class SessionInfo(Contract):
    role: SessionRole
    display_name: str | None
    expires_at: datetime | None = Field(
        description="When the engineer or admin role ends (the session goes on as a visitor); "
        "null for a visitor."
    )
    csrf_token: str | None
    workspace: WorkspaceInfo | None = Field(
        None, description="This device's workspace; null before the first visit is recorded."
    )


class GuestSessionCreate(Contract):
    display_name: str | None = Field(None, min_length=1, max_length=40)


class LoginRequest(Contract):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=256)
