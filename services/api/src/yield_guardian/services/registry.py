"""The services the API is running with. A missing service answers 503 (problem code not_ready)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from yield_guardian.contracts.methods import BundleInfo
from yield_guardian.contracts.services import (
    ChatResponder,
    InvestigationRunner,
    KnowledgeService,
    LlmAdmin,
    SecomService,
    WaferService,
)
from yield_guardian.core.settings import Settings
from yield_guardian.live.protocols import RunReader
from yield_guardian.live.runs import RunService
from yield_guardian.live.uploads import UploadService
from yield_guardian.services.protocols import (
    AlarmService,
    AuditLog,
    InvestigationStore,
    MethodsService,
    SessionManager,
    WorkOrderStore,
)


class Resource(Protocol):
    """Something with a lifetime (database pool, job worker, run executor).

    The app starts resources in list order when it starts and stops them in reverse order.
    """

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


@dataclass(slots=True)
class ServiceRegistry:
    settings: Settings
    secom: SecomService | None = None
    wafer: WaferService | None = None
    knowledge: KnowledgeService | None = None
    alarms: AlarmService | None = None
    investigations: InvestigationStore | None = None
    runner: InvestigationRunner | None = None
    work_orders: WorkOrderStore | None = None
    audit: AuditLog | None = None
    sessions: SessionManager | None = None
    methods: MethodsService | None = None
    chat: ChatResponder | None = None
    llm: LlmAdmin | None = None
    run_reader: RunReader | None = None
    runs: RunService | None = None
    uploads: UploadService | None = None
    bundles: list[BundleInfo] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    problems: dict[str, str] = field(default_factory=dict)
    database_ok: bool | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
