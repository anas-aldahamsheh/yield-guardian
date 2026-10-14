"""Health, readiness and application metadata."""

from datetime import datetime
from typing import Literal

from yield_guardian.contracts.base import Contract
from yield_guardian.contracts.methods import BundleInfo


class Health(Contract):
    status: Literal["ok"]


class ReadinessCheck(Contract):
    name: str
    ok: bool
    detail: str | None


class Readiness(Contract):
    ready: bool
    checks: list[ReadinessCheck]


class Features(Contract):
    live_investigations: bool
    chat: bool
    admin_login: bool


class Meta(Contract):
    app_name: str
    version: str
    git_commit: str | None
    started_at: datetime
    bundles: list[BundleInfo]
    features: Features
