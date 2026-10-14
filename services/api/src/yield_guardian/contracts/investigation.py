"""Investigations: evidence, the report contract, verification, steps, decisions and SSE events.

Report numbers: `NumberRef.value` is the number exactly as written in the text. When `unit` is
"%", the evidence holds value / 100. `path` is an RFC 6901 JSON Pointer into `Evidence.data`.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, JsonValue, RootModel

from yield_guardian.contracts.base import (
    BundleRef,
    Contract,
    Count,
    EvidenceId,
    InvestigationId,
    Problem,
    WorkOrderId,
)
from yield_guardian.contracts.models import CallUsage, RoleName, Usage

ToolName = Literal[
    "get_unit",
    "get_risk",
    "get_shap",
    "get_feature_groups",
    "get_fdc_window",
    "get_contributions",
    "get_sensor_health",
    "get_wafer_prediction",
    "get_similar_wafers",
    "get_lot_stats",
    "search_knowledge",
]
Strength = Literal["strong", "moderate", "weak"]
TriggerKind = Literal["alarm", "unit", "wafer", "lot"]
InvestigationStatus = Literal[
    "queued", "running", "awaiting_decision", "approved", "rejected", "failed"
]
GraphNode = Literal["triage", "plan", "evidence", "write", "verify", "decision"]
StepStatus = Literal["running", "completed", "failed", "skipped"]
Verdict = Literal["approve", "reject"]
IssueCode = Literal[
    "schema",
    "number_not_listed",
    "number_mismatch",
    "unknown_evidence",
    "missing_citation",
    "causal_wording",
    "unsupported_claim",
    "verifier_unavailable",
]
ClaimVerdictValue = Literal["supported", "partially_supported", "unsupported", "not_checked"]


class Evidence(Contract):
    """A tool result stored as evidence. The report may cite only evidence IDs."""

    evidence_id: EvidenceId
    investigation_id: InvestigationId | None = Field(
        description="Null for evidence gathered by the chat."
    )
    tool: ToolName
    arguments: dict[str, JsonValue]
    data: dict[str, JsonValue] = Field(description="The tool output as JSON (a contract model).")
    summary: str = Field(description="One line written by code, not by a language model.")
    created_at: datetime
    source: BundleRef | None


class Finding(Contract):
    claim: str = Field(min_length=1, max_length=600)
    evidence_ids: list[EvidenceId] = Field(min_length=1)
    strength: Strength


class Action(Contract):
    action: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=600)
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class NumberRef(Contract):
    value: float = Field(description="The number as written in the text.")
    as_written: str = Field(min_length=1, max_length=40, examples=["12.5%"])
    unit: str | None = Field(examples=["%", "probability", "log-odds", "units", "sensors"])
    evidence_id: EvidenceId
    path: str = Field(pattern=r"^(/[^/]*)*$", examples=["/contributions/0/shap"])


class Report(Contract):
    summary: str = Field(min_length=1, max_length=1200)
    findings: list[Finding]
    actions: list[Action]
    numbers: list[NumberRef]
    limitations: list[str]


class VerificationIssue(Contract):
    code: IssueCode
    severity: Literal["error", "warning"]
    location: str = Field(examples=["findings[1].claim"])
    message: str


class ClaimVerdict(Contract):
    finding_index: Count
    verdict: ClaimVerdictValue
    note: str | None


class Verification(Contract):
    passed: bool
    rounds: Count = Field(description="Writer revisions used (at most 2).")
    numbers_checked: Count
    numbers_matched: Count
    issues: list[VerificationIssue] = Field(
        description="Remaining issues; shown flagged on the report."
    )
    claims: list[ClaimVerdict]
    verifier_model: str | None


class InvestigationStep(Contract):
    index: Count = Field(
        description="Order of the step; a step is sent again with the same index when it ends."
    )
    node: GraphNode
    status: StepStatus
    title: str = Field(
        description="Written by code, for example 'Read the SHAP explanation of unit 1043'."
    )
    started_at: datetime
    finished_at: datetime | None
    tool: ToolName | None
    evidence_ids: list[EvidenceId]
    llm: list[CallUsage]


class InvestigationTrigger(Contract):
    kind: TriggerKind
    ref: str = Field(
        min_length=1,
        max_length=80,
        description="Alarm ID, unit ID, wafer ID or lot, depending on `kind`.",
        examples=["AL-1043-t2"],
    )
    question: str | None = Field(None, max_length=500)


class InvestigationCreate(Contract):
    trigger: InvestigationTrigger


class Decision(Contract):
    verdict: Verdict
    actions: list[Count] = Field(
        description="Indexes of the report actions approved (empty on reject)."
    )
    note: str | None
    decided_by: str
    decided_at: datetime


class DecisionCreate(Contract):
    verdict: Verdict
    actions: list[Count] | None = Field(
        None, description="Indexes of report actions; null approves all."
    )
    note: str | None = Field(None, max_length=2000)


class RoleModel(Contract):
    role: RoleName
    model_id: str


class InvestigationSummary(Contract):
    investigation_id: InvestigationId
    title: str
    status: InvestigationStatus
    trigger: InvestigationTrigger
    created_at: datetime
    updated_at: datetime
    recorded: bool = Field(
        description="A recorded run, generated once and replayed, not a live call."
    )
    models: list[RoleModel]
    usage: Usage | None
    work_order_id: WorkOrderId | None


class Investigation(InvestigationSummary):
    steps: list[InvestigationStep]
    evidence: list[Evidence]
    report: Report | None
    verification: Verification | None
    decision: Decision | None
    error: Problem | None


class InvestigationPage(Contract):
    items: list[InvestigationSummary]
    next_cursor: str | None = None
    total: Count


class StatusEvent(Contract):
    type: Literal["status"]
    seq: Count
    at: datetime
    status: InvestigationStatus


class StepEvent(Contract):
    type: Literal["step"]
    seq: Count
    at: datetime
    step: InvestigationStep


class EvidenceEvent(Contract):
    type: Literal["evidence"]
    seq: Count
    at: datetime
    evidence: Evidence


class ReportEvent(Contract):
    """A report draft from the writer; `round` 0 is the first draft."""

    type: Literal["report"]
    seq: Count
    at: datetime
    round: Count
    report: Report


class VerificationEvent(Contract):
    type: Literal["verification"]
    seq: Count
    at: datetime
    round: Count
    verification: Verification


class DecisionEvent(Contract):
    type: Literal["decision"]
    seq: Count
    at: datetime
    decision: Decision
    work_order_id: WorkOrderId | None


class ErrorEvent(Contract):
    type: Literal["error"]
    seq: Count
    at: datetime
    problem: Problem


class EndEvent(Contract):
    """Last event of a stream: the investigation is waiting for a decision or finished."""

    type: Literal["end"]
    seq: Count
    at: datetime
    status: InvestigationStatus


class InvestigationEvent(
    RootModel[
        Annotated[
            StatusEvent
            | StepEvent
            | EvidenceEvent
            | ReportEvent
            | VerificationEvent
            | DecisionEvent
            | ErrorEvent
            | EndEvent,
            Field(discriminator="type"),
        ]
    ]
):
    """An event on GET /investigations/{id}/events (SSE: `event` is the type, `id` is `seq`)."""


InvestigationEventPayload = (
    StatusEvent
    | StepEvent
    | EvidenceEvent
    | ReportEvent
    | VerificationEvent
    | DecisionEvent
    | ErrorEvent
    | EndEvent
)
