"""The services the API is running with. A missing service answers 503 (problem code not_ready)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

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
from yield_guardian.services.protocols import (
    AuditLog,
    InvestigationStore,
    LineService,
    MethodsService,
    SessionManager,
    WorkOrderStore,
)


@dataclass(slots=True)
class ServiceRegistry:
    settings: Settings
    secom: SecomService | None = None
    wafer: WaferService | None = None
    knowledge: KnowledgeService | None = None
    line: LineService | None = None
    investigations: InvestigationStore | None = None
    runner: InvestigationRunner | None = None
    work_orders: WorkOrderStore | None = None
    audit: AuditLog | None = None
    sessions: SessionManager | None = None
    methods: MethodsService | None = None
    chat: ChatResponder | None = None
    llm: LlmAdmin | None = None
    bundles: list[BundleInfo] = field(default_factory=list)
    database_ok: bool | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
