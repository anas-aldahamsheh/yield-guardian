"""Sessions. Everything is viewable without one; actions need "Try as engineer" or an admin login.

The session lives in an HttpOnly, SameSite=Lax cookie. Unsafe requests carry `csrf_token` in the
X-CSRF-Token header.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field, SecretStr

from yield_guardian.contracts.base import Contract

SessionRole = Literal["visitor", "engineer", "admin"]


class SessionInfo(Contract):
    role: SessionRole
    display_name: str | None
    expires_at: datetime | None
    csrf_token: str | None


class GuestSessionCreate(Contract):
    display_name: str | None = Field(None, min_length=1, max_length=40)


class LoginRequest(Contract):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=256)
