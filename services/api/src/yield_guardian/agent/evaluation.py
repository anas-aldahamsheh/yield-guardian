"""Offline-built, explicitly run evaluation of one model in one role.

A task set is a JSON file of hand-written cases with known answers (``scripts/evaluation/``).
Two roles have answers code can score without a model:

* ``router``: the intent the router model gives a question equals the expected intent;
* ``verifier``: the verdict the verifier model gives each finding, against its cited evidence,
  falls in the expected class (``supported``, or ``not_supported`` for ``unsupported`` and
  ``partially_supported``).

A task succeeds when every answer is right. A violation is a task where the model gave no usable
answer (an error, an answer that failed the output schema, or a finding left without a verdict).
The success rate is an :class:`Estimate` with a Wilson score interval. Points come from the
documented pricing and the usage the server reported; calls without usage are counted, not
guessed.

The cost is bounded before anything is sent (:func:`estimate_cost`): every request body is
built exactly as the gateway will send it, and its UTF-8 size bounds its prompt tokens (a
byte-level tokenizer never makes more tokens than bytes), while ``max_tokens`` bounds the
completion (reasoning included). Running a task set spends shared quota, so only
``scripts/run_evaluation.py`` runs one, never CI and never a test against the endpoint.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from yield_guardian.agent.router import ROUTER_SCHEMA_NAME, Intent, RouterAnswer, router_request
from yield_guardian.agent.verifier import (
    CLAIMS_SCHEMA_NAME,
    ClaimChecks,
    ReportVerifier,
    verifier_request,
)
from yield_guardian.contracts.base import Estimate, EvidenceId
from yield_guardian.contracts.investigation import (
    Evidence,
    Finding,
    Report,
    Strength,
    ToolName,
)
from yield_guardian.contracts.models import EvaluationResult
from yield_guardian.llm.calllog import LlmCallRecord
from yield_guardian.llm.errors import LlmError
from yield_guardian.llm.gateway import CallOptions, LlmGateway
from yield_guardian.llm.messages import ChatRequest, ResponseFormat
from yield_guardian.llm.profiles import ProfileCatalog
from yield_guardian.llm.registry import (
    InMemoryRoleAssignmentStore,
    ModelChoice,
    ModelRegistry,
    ResponseMode,
    Role,
    RoleAssignment,
    choice_for,
)
from yield_guardian.llm.request_builder import build_chat_request
from yield_guardian.llm.structured import strict_json_schema

WILSON_METHOD = "Wilson score interval"
EVALUATED_ROLES: frozenset[Role] = frozenset({Role.ROUTER, Role.VERIFIER})


class EvaluationError(ValueError):
    """The evaluation cannot run as asked (unknown model, no price, invalid task set...)."""


# -- task sets ----------------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RouterTask(_Strict):
    id: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=1, max_length=500)
    expected: Intent


class TaskEvidence(_Strict):
    evidence_id: EvidenceId
    tool: ToolName
    arguments: dict[str, JsonValue]
    data: dict[str, JsonValue]
    summary: str = Field(min_length=1)


ExpectedVerdict = Literal["supported", "not_supported"]


class TaskFinding(_Strict):
    claim: str = Field(min_length=1, max_length=600)
    evidence_ids: list[EvidenceId] = Field(min_length=1)
    strength: Strength
    expected: ExpectedVerdict


class VerifierTask(_Strict):
    id: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=1200)
    evidence: list[TaskEvidence] = Field(min_length=1)
    findings: list[TaskFinding] = Field(min_length=1)


class RouterTaskSet(_Strict):
    name: str = Field(pattern=r"^[a-z0-9_-]{1,60}$")
    role: Literal["router"]
    description: str
    tasks: list[RouterTask] = Field(min_length=1)


class VerifierTaskSet(_Strict):
    name: str = Field(pattern=r"^[a-z0-9_-]{1,60}$")
    role: Literal["verifier"]
    description: str
    tasks: list[VerifierTask] = Field(min_length=1)


TaskSet = Annotated[RouterTaskSet | VerifierTaskSet, Field(discriminator="role")]
_TASK_SET: TypeAdapter[RouterTaskSet | VerifierTaskSet] = TypeAdapter(TaskSet)


def check_task_set(task_set: RouterTaskSet | VerifierTaskSet) -> None:
    ids = [task.id for task in task_set.tasks]
    if len(ids) != len(set(ids)):
        raise EvaluationError(f"{task_set.name}: task IDs repeat")
    if isinstance(task_set, VerifierTaskSet):
        for task in task_set.tasks:
            known = [e.evidence_id for e in task.evidence]
            if len(known) != len(set(known)):
                raise EvaluationError(f"{task.id}: evidence IDs repeat")
            cited = {i for f in task.findings for i in f.evidence_ids}
            if not cited <= set(known):
                missing = ", ".join(sorted(cited - set(known)))
                raise EvaluationError(f"{task.id}: findings cite unknown evidence {missing}")


def parse_task_set(text: str) -> RouterTaskSet | VerifierTaskSet:
    task_set = _TASK_SET.validate_json(text)
    check_task_set(task_set)
    return task_set


def load_task_set(path: Path) -> RouterTaskSet | VerifierTaskSet:
    return parse_task_set(path.read_text(encoding="utf-8"))


def task_role(task_set: RouterTaskSet | VerifierTaskSet) -> Role:
    return Role(task_set.role)


# -- requests -----------------------------------------------------------------------------------

_EVIDENCE_TIME = datetime(2000, 1, 1, tzinfo=UTC)
"""Evaluation evidence is not from any run; the verifier prompt does not show this time."""


def task_evidence(task: VerifierTask) -> dict[str, Evidence]:
    return {
        item.evidence_id: Evidence(
            evidence_id=item.evidence_id,
            investigation_id=None,
            tool=item.tool,
            arguments=item.arguments,
            data=item.data,
            summary=item.summary,
            created_at=_EVIDENCE_TIME,
            source=None,
        )
        for item in task.evidence
    }


def task_report(task: VerifierTask) -> Report:
    findings = [
        Finding(claim=f.claim, evidence_ids=list(f.evidence_ids), strength=f.strength)
        for f in task.findings
    ]
    return Report(summary=task.summary, findings=findings, actions=[], numbers=[], limitations=[])


@dataclass(frozen=True, slots=True)
class _Output:
    name: str
    schema: dict[str, Any]


def task_requests(
    task_set: RouterTaskSet | VerifierTaskSet,
) -> list[tuple[str, ChatRequest, _Output]]:
    """Each task's request and output schema, exactly as the agent code builds them."""
    if isinstance(task_set, RouterTaskSet):
        router_output = _Output(ROUTER_SCHEMA_NAME, strict_json_schema(RouterAnswer))
        return [(t.id, router_request(t.question), router_output) for t in task_set.tasks]
    claims_output = _Output(CLAIMS_SCHEMA_NAME, strict_json_schema(ClaimChecks))
    return [
        (t.id, verifier_request(task_report(t), task_evidence(t)), claims_output)
        for t in task_set.tasks
    ]


def prepared(request: ChatRequest, choice: ModelChoice, output: _Output) -> ChatRequest:
    """The request with the chain entry's effort and response format, as the gateway sends it."""
    update: dict[str, Any] = {"reasoning_effort": choice.reasoning_effort}
    if choice.response_mode is ResponseMode.JSON_SCHEMA:
        update["response_format"] = ResponseFormat.strict_schema(output.name, output.schema)
    elif choice.response_mode is ResponseMode.JSON_OBJECT:
        update["response_format"] = ResponseFormat.json_object()
    else:
        raise EvaluationError(f"{choice.model}: structured roles need a JSON response mode")
    return request.model_copy(update=update)


# -- the model under evaluation -----------------------------------------------------------------


def evaluated_choice(role: Role, model: str, catalog: ProfileCatalog) -> ModelChoice:
    if role not in EVALUATED_ROLES:
        raise EvaluationError(f"no scored task sets for the {role} role")
    profile = catalog.get(model)
    if profile is None:
        raise EvaluationError(f"{model} is not a documented model")
    return choice_for(role, profile)


async def single_model_registry(role: Role, model: str, catalog: ProfileCatalog) -> ModelRegistry:
    """A registry whose chain for ``role`` is ``model`` alone, so no fallback model can answer
    in its place. Refuses a model the role cannot use."""
    choice = evaluated_choice(role, model, catalog)
    assignment = RoleAssignment(role=role, chain=(choice,))
    registry = ModelRegistry(catalog, InMemoryRoleAssignmentStore([assignment]))
    warnings = await registry.load()
    if registry.assignment(role).chain != (choice,):
        raise EvaluationError(f"{model} cannot serve the {role} role: " + "; ".join(warnings))
    return registry


# -- cost bound ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostEstimate:
    model: str
    tasks: int
    calls: int
    prompt_bytes: int
    max_output_tokens: int
    points_upper_bound: float
    assumptions: tuple[str, ...]


def estimate_cost(
    task_set: RouterTaskSet | VerifierTaskSet, model: str, catalog: ProfileCatalog
) -> CostEstimate:
    """An upper bound of the points the task set can spend on ``model``: one call per task
    (no retry is billed twice: a retried request failed before it was served)."""
    role = task_role(task_set)
    choice = evaluated_choice(role, model, catalog)
    profile = catalog.get(model)
    if profile is None or profile.pricing is None:
        raise EvaluationError(f"{model} has no documented price; the cost cannot be bounded")
    pricing = profile.pricing
    prompt_bytes = 0
    max_output = 0
    for _, request, output in task_requests(task_set):
        body = build_chat_request(profile, prepared(request, choice, output)).body
        prompt_bytes += len(json.dumps(body, ensure_ascii=False).encode())
        max_output += int(body["max_tokens"])
    points = (prompt_bytes * pricing.input_per_mtok + max_output * pricing.output_per_mtok) / 1e6
    return CostEstimate(
        model=model,
        tasks=len(task_set.tasks),
        calls=len(task_set.tasks),
        prompt_bytes=prompt_bytes,
        max_output_tokens=max_output,
        points_upper_bound=points,
        assumptions=(
            "prompt tokens are at most the UTF-8 bytes of the whole request body",
            "completion tokens, reasoning included, are at most max_tokens",
            "cached prompt tokens are billed at the full input price",
            "one served call per task; the cache is bypassed",
        ),
    )


# -- scoring ------------------------------------------------------------------------------------


def wilson(successes: int, n: int, *, level: float = 0.95) -> Estimate:
    """The success rate with its Wilson score interval (sound at 0 and n successes too)."""
    if n <= 0:
        raise EvaluationError("an evaluation needs at least one task")
    if not 0 <= successes <= n:
        raise EvaluationError("successes must be between 0 and n")
    z = NormalDist().inv_cdf(0.5 + level / 2)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return Estimate(
        value=p,
        ci_low=max(0.0, centre - half),
        ci_high=min(1.0, centre + half),
        ci_level=level,
        method=WILSON_METHOD,
        n=n,
        note=None,
    )


def verdict_class(verdict: str) -> ExpectedVerdict | None:
    if verdict == "supported":
        return "supported"
    if verdict in ("unsupported", "partially_supported"):
        return "not_supported"
    return None


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    task_id: str
    success: bool
    violation: bool
    answer: str
    """What the model answered, as code read it (an intent, or verdict classes)."""
    expected: str


@dataclass
class EvaluationRun:
    result: EvaluationResult
    outcomes: list[TaskOutcome]
    estimate: CostEstimate
    calls: list[LlmCallRecord] = field(default_factory=list)

    @property
    def calls_without_usage(self) -> int:
        return sum(1 for r in self.calls if r.sent and not r.usage_known)

    def to_json(self) -> dict[str, Any]:
        return {
            "result": self.result.model_dump(mode="json"),
            "calls": len(self.calls),
            "calls_without_usage": self.calls_without_usage,
            "points_upper_bound": self.estimate.points_upper_bound,
            "outcomes": [
                {
                    "task_id": o.task_id,
                    "success": o.success,
                    "violation": o.violation,
                    "answer": o.answer,
                    "expected": o.expected,
                }
                for o in self.outcomes
            ],
        }


async def _router_task(gateway: LlmGateway, task: RouterTask, options: CallOptions) -> TaskOutcome:
    try:
        out = await gateway.complete_structured(
            Role.ROUTER,
            router_request(task.question),
            RouterAnswer,
            schema_name=ROUTER_SCHEMA_NAME,
            options=options,
        )
    except LlmError as exc:
        return TaskOutcome(task.id, False, True, f"no answer ({type(exc).__name__})", task.expected)
    intent = out.value.intent
    return TaskOutcome(task.id, intent == task.expected, False, intent, task.expected)


async def _verifier_task(
    gateway: LlmGateway, task: VerifierTask, options: CallOptions
) -> TaskOutcome:
    check = await ReportVerifier(gateway).model_check(
        task_report(task), task_evidence(task), writer_model=None, options=options
    )
    expected = [f.expected for f in task.findings]
    got = [verdict_class(c.verdict) for c in check.claims]
    violation = len(got) != len(expected) or any(g is None for g in got)
    answer = ",".join(g or "no_verdict" for g in got)
    return TaskOutcome(task.id, not violation and got == expected, violation, answer, ",".join(expected))  # fmt: skip


async def run_task_set(
    gateway: LlmGateway,
    task_set: RouterTaskSet | VerifierTaskSet,
    model: str,
    *,
    wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> EvaluationRun:
    """Run every task once on ``model`` (the gateway's chain for the role must be that model
    alone: see :func:`single_model_registry`), bypassing the cache."""
    role = task_role(task_set)
    if gateway.registry.assignment(role).chain != (evaluated_choice(role, model, gateway.registry.catalog),):  # fmt: skip
        raise EvaluationError(f"the gateway's {role} chain is not {model} alone")
    estimate = estimate_cost(task_set, model, gateway.registry.catalog)
    run_at = wall_clock()
    records: list[LlmCallRecord] = []
    outcomes: list[TaskOutcome] = []
    for task in task_set.tasks:
        options = CallOptions(
            correlation_id=f"evaluation:{task_set.name}:{task.id}",
            use_cache=False,
            on_record=records.append,
        )
        if isinstance(task, RouterTask):
            outcomes.append(await _router_task(gateway, task, options))
        else:
            outcomes.append(await _verifier_task(gateway, task, options))
    return EvaluationRun(
        result=summarise(task_set, model, outcomes, records, run_at),
        outcomes=outcomes,
        estimate=estimate,
        calls=records,
    )


def summarise(
    task_set: RouterTaskSet | VerifierTaskSet,
    model: str,
    outcomes: Sequence[TaskOutcome],
    records: Sequence[LlmCallRecord],
    run_at: datetime,
) -> EvaluationResult:
    sent = [r for r in records if r.sent]
    known = [r for r in sent if r.usage_known]
    rate = wilson(sum(o.success for o in outcomes), len(outcomes))
    without = len(sent) - len(known)
    notes = [f"hand-written task set '{task_set.name}', one call per task, cache bypassed"]
    if without:
        notes.append(f"{without} call(s) reported no usage and are not in the token or point sums")
    return EvaluationResult(
        role=task_set.role,
        model_id=model,
        task_set=task_set.name,
        tasks=len(outcomes),
        success_rate=rate.model_copy(update={"note": "; ".join(notes)}),
        violations=sum(o.violation for o in outcomes),
        latency_ms_p50=statistics.median(r.latency_ms for r in sent) if sent else None,
        tokens_in=sum(r.tokens_in or 0 for r in known),
        tokens_out=sum(r.tokens_out or 0 for r in known),
        points=sum(r.points for r in known if r.points is not None),
        run_at=run_at,
    )
