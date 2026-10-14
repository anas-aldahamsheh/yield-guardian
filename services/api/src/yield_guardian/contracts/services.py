"""Interfaces between the API, the science services and the AI layer.

The lead implements `SecomService`, `WaferService` and `KnowledgeService` (read-only, typed, every
value from a verified artifact bundle or the database). The AI layer calls them through its tools
and implements `InvestigationRunner`, `ChatResponder` and `LlmAdmin`, which the API calls.

Services never return units after the plant clock's position: those have not come off the line.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from yield_guardian.contracts.base import Problem, ProblemCode
from yield_guardian.contracts.chat import ChatEventPayload, ChatRequest
from yield_guardian.contracts.investigation import (
    Decision,
    Evidence,
    InvestigationStatus,
    InvestigationStep,
    InvestigationTrigger,
    Report,
    Verification,
)
from yield_guardian.contracts.knowledge import KnowledgeSearchResult, PatternCauses
from yield_guardian.contracts.line import RiskBand
from yield_guardian.contracts.models import (
    CatalogModel,
    Evaluations,
    RoleAssignment,
    RoleAssignmentUpdate,
    RoleName,
    UsageReport,
)
from yield_guardian.contracts.secom import (
    Explanation,
    FdcContributions,
    FdcSeries,
    FdcStatistic,
    OperatingPoints,
    SecomMetrics,
    SensorGroups,
    SensorHealthReport,
    SensorSeries,
    SensorStatus,
    UnitDetail,
    UnitPage,
    UnitRisk,
)
from yield_guardian.contracts.session import SessionInfo
from yield_guardian.contracts.wafer import (
    LotDetail,
    LotPage,
    SimilarWafers,
    WaferDetail,
    WaferHero,
    WaferLabel,
    WaferMetrics,
    WaferPage,
    WaferPrediction,
)


class ServiceError(Exception):
    """Base of every error a service raises. The API maps it to problem+json; tools report it."""

    code: ProblemCode = "internal_error"
    status: int = 500
    title: str = "Internal error"

    def __init__(self, detail: str, *, retry_after_s: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.retry_after_s = retry_after_s

    def problem(self, instance: str | None = None) -> Problem:
        return Problem(
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=instance,
            code=self.code,
            retry_after_s=self.retry_after_s,
        )


class InvalidArgumentError(ServiceError):
    code = "bad_request"
    status = 400
    title = "Invalid argument"


class NotFoundError(ServiceError):
    code = "not_found"
    status = 404
    title = "Not found"


class NotReadyError(ServiceError):
    """A data or model bundle is not loaded, or a dependency is not configured."""

    code = "not_ready"
    status = 503
    title = "Not ready"


class UpstreamError(ServiceError):
    """The model service failed after the retries; `retry_after_s` when it said how long to wait."""

    code = "upstream_error"
    status = 502
    title = "Model service error"


@runtime_checkable
class SecomService(Protocol):
    async def list_units(
        self,
        *,
        from_seq: int | None = None,
        to_seq: int | None = None,
        band: RiskBand | None = None,
        cursor: str | None = None,
        limit: int = 200,
    ) -> UnitPage: ...

    async def get_unit(self, unit_id: int) -> UnitDetail: ...

    async def get_risk(self, unit_id: int) -> UnitRisk: ...

    async def get_explanation(self, unit_id: int, *, top_k: int = 15) -> Explanation: ...

    async def get_feature_groups(
        self, *, significant_only: bool = False, limit: int = 20
    ) -> SensorGroups: ...

    async def get_fdc_series(
        self, *, from_seq: int | None = None, to_seq: int | None = None
    ) -> FdcSeries: ...

    async def get_contributions(
        self, unit_id: int, *, statistic: FdcStatistic = "t2", top_k: int = 15
    ) -> FdcContributions: ...

    async def get_sensor_health(
        self,
        *,
        sensors: Sequence[str] | None = None,
        statuses: Sequence[SensorStatus] | None = None,
    ) -> SensorHealthReport: ...

    async def get_sensor_series(
        self, sensor: str, *, from_seq: int | None = None, to_seq: int | None = None
    ) -> SensorSeries: ...

    async def get_operating_points(self) -> OperatingPoints: ...

    async def get_metrics(self) -> SecomMetrics: ...


@runtime_checkable
class WaferService(Protocol):
    async def list_wafers(
        self,
        *,
        lot: str | None = None,
        label: WaferLabel | None = None,
        unknown: bool | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> WaferPage: ...

    async def get_wafer(self, wafer_id: str) -> WaferDetail: ...

    async def get_hero(self) -> WaferHero: ...

    async def get_prediction(self, wafer_id: str) -> WaferPrediction: ...

    async def get_similar(self, wafer_id: str, *, k: int = 10) -> SimilarWafers: ...

    async def list_lots(
        self, *, flagged_only: bool = False, cursor: str | None = None, limit: int = 100
    ) -> LotPage: ...

    async def get_lot(self, lot: str) -> LotDetail: ...

    async def get_metrics(self) -> WaferMetrics: ...


@runtime_checkable
class KnowledgeService(Protocol):
    async def search(self, query: str, *, limit: int = 5) -> KnowledgeSearchResult: ...

    async def pattern_causes(self, label: WaferLabel | None = None) -> PatternCauses: ...


@dataclass(frozen=True, slots=True)
class ScienceServices:
    """What the investigator's read-only tools may call."""

    secom: SecomService
    wafer: WaferService
    knowledge: KnowledgeService


class InvestigationSink(Protocol):
    """Receives investigation progress. The API persists each call and streams it as an SSE event.

    Steps are sent when they start and again, with the same index, when they end.
    """

    async def status(self, status: InvestigationStatus) -> None: ...

    async def step(self, step: InvestigationStep) -> None: ...

    async def evidence(self, evidence: Evidence) -> None: ...

    async def report(self, report: Report, *, round: int) -> None: ...

    async def verification(self, verification: Verification, *, round: int) -> None: ...

    async def error(self, problem: Problem) -> None: ...


class InvestigationRunner(Protocol):
    """The investigator graph (triage, plan, evidence, write, verify, human decision)."""

    async def run(
        self, investigation_id: str, trigger: InvestigationTrigger, sink: InvestigationSink
    ) -> None:
        """Run until the graph waits for the human decision (status `awaiting_decision`).

        Model or tool failures are reported through `sink.error` and status `failed`, not raised.
        """
        ...

    async def resume(
        self, investigation_id: str, decision: Decision, sink: InvestigationSink
    ) -> None:
        """Resume the paused graph with the engineer's decision; the graph records it and ends.

        The API then opens the work order, writes the audit log and sends the decision event.
        """
        ...


class ChatResponder(Protocol):
    def answer(
        self, request: ChatRequest, *, session: SessionInfo
    ) -> AsyncIterator[ChatEventPayload]:
        """Stream the answer: route, tool and citation events, tokens, then done (or refusal or error)."""
        ...


class LlmAdmin(Protocol):
    async def catalog(self) -> list[CatalogModel]: ...

    async def roles(self) -> list[RoleAssignment]: ...

    async def set_role(
        self, role: RoleName, update: RoleAssignmentUpdate, *, actor: str
    ) -> RoleAssignment: ...

    async def usage(self) -> UsageReport: ...

    async def evaluations(self) -> Evaluations: ...

    async def live_calls_available(self) -> bool:
        """A Token Factory key is configured. The product never limits calls (PLAN D-009)."""
        ...
