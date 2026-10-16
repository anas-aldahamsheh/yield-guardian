"""The investigator graph (PLAN 7.3): triage, plan, gather evidence, write, verify, decide.

::

    triage -> plan <-> evidence -> write -> verify -> await_decision -> decision -> end
                                     ^        |
                                     +--------+  (at most two revisions)

* **triage** is code: one read-only tool call chosen from the trigger (the unit behind an
  alarm, the unit, the wafer's prediction or the lot's tests); for an alarm raised in a run, two
  (the run, then the unit, wafer or lot the alarm is about). It costs no model call.
* **plan** asks the investigator model which tools to call next, with the evidence so far as
  data. It answers with tool calls, or with no tool call when it has enough.
* **evidence** runs those calls through :class:`~yield_guardian.agent.tools.ToolExecutor`.
  Every call counts toward the limit of eight, the triage call included, whether it returns
  evidence, is refused (unknown tool, invalid arguments), fails in the service or repeats an
  earlier call. Calls past the limit are not run and are shown as skipped steps.
* **write** asks the writer for the report (and for a revision when verification failed).
* **verify** runs the code checks and the cross-family verifier model
  (:mod:`yield_guardian.agent.verifier`). It sends the report to the sink only now, with every
  value that failed a check hidden, followed by its verification.
* **await_decision** marks the investigation as waiting; **decision** pauses
  (:func:`langgraph.types.interrupt`) until :meth:`InvestigatorRunner.resume` delivers the
  engineer's decision, which it records (the API sends the approved or rejected status).
  LangGraph re-runs an interrupted node from its start when it resumes, so ``decision`` does
  nothing before the interrupt and the waiting side effects live in ``await_decision``.

The model recommends; it cannot act. The engineer's decision is the only way out of the graph,
and opening a work order happens in the API after it.

State is plain JSON (contract models dumped in ``mode="json"``) so any LangGraph checkpointer
can hold it: ``InMemorySaver`` in tests, ``AsyncPostgresSaver`` in production (wired by the
API). The thread ID is the investigation ID.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from yield_guardian.agent.prompts import INVESTIGATOR_SYSTEM, data_json, data_message
from yield_guardian.agent.run_results import parse_run_alarm_ref
from yield_guardian.agent.run_tools import alarm_item_call, read_run
from yield_guardian.agent.tools import (
    ALL_TOOL_NAMES,
    SCIENCE_TOOL_NAMES,
    EvidenceLedger,
    ToolExecutor,
    ToolOutcome,
    model_view,
    tool_specs,
)
from yield_guardian.agent.verifier import ReportVerifier
from yield_guardian.agent.writer import WRITER_MAX_TOKENS, ReportWriter, WriterInput
from yield_guardian.contracts.base import Problem
from yield_guardian.contracts.investigation import (
    ClaimVerdict,
    Decision,
    Evidence,
    GraphNode,
    InvestigationStep,
    InvestigationTrigger,
    Report,
    StepStatus,
    ToolName,
    Verification,
    VerificationIssue,
)
from yield_guardian.contracts.services import InvestigationSink, ScienceServices, ServiceError
from yield_guardian.llm.calllog import LlmCallRecord, to_call_usage
from yield_guardian.llm.errors import LlmError, NoModelAvailableError, TokenFactoryHttpError
from yield_guardian.llm.gateway import CallOptions, LlmGateway
from yield_guardian.llm.messages import ChatMessage, ChatRequest
from yield_guardian.llm.registry import Role

log = structlog.get_logger(__name__)

_ALARM = re.compile(r"^AL-(?P<unit>[0-9]+)-")


@dataclass(frozen=True, slots=True)
class InvestigationLimits:
    max_tool_steps: int = 8
    """Tool calls per investigation, the triage call included."""
    max_revisions: int = 2
    """Writer revisions after the first draft."""
    plan_max_tokens: int = 2048
    writer_max_tokens: int = WRITER_MAX_TOKENS

    def __post_init__(self) -> None:
        if self.max_tool_steps < 1 or self.max_revisions < 0:
            raise ValueError("an investigation needs at least one tool step")


class InvestigationState(TypedDict):
    investigation_id: str
    trigger: dict[str, Any]
    evidence: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    """The planning conversation after the system prompt: the data message, then the model's
    tool calls and the tool results."""
    pending: list[dict[str, Any]]
    """Tool calls the last plan asked for: ``{"id", "name", "arguments"}``."""
    tool_steps: int
    next_step: int
    round: int
    report: dict[str, Any] | None
    writer_model: str | None
    issues: list[dict[str, Any]]
    """Errors of the last verification, sent to the writer with the revision request."""
    revise: bool
    verification: dict[str, Any] | None
    decision_step: dict[str, Any] | None
    decision: dict[str, Any] | None
    failure: dict[str, Any] | None
    """Problem details when the investigation failed; the runner reports it."""
    as_of: int | None
    """For a recorded run: the line position (the alarm's sequence) its tools read the data as
    of. None for a live run, whose tools read every unit."""


def initial_state(
    investigation_id: str, trigger: InvestigationTrigger, *, as_of: int | None = None
) -> InvestigationState:
    return InvestigationState(
        investigation_id=investigation_id,
        trigger=trigger.model_dump(mode="json"),
        evidence=[],
        messages=[],
        pending=[],
        tool_steps=0,
        next_step=0,
        round=0,
        report=None,
        writer_model=None,
        issues=[],
        revise=False,
        verification=None,
        decision_step=None,
        decision=None,
        failure=None,
        as_of=as_of,
    )


def services_as_of(services: ScienceServices, position: int | None) -> ScienceServices:
    """The services a run's tools read: as of ``position`` for a recorded run, else unchanged.
    Only the SECOM service follows the line; a stand-in without ``as_of`` is left as it is
    (it refuses every read anyway)."""
    if position is None:
        return services
    view = getattr(type(services.secom), "as_of", None)  # the class, not a stand-in's __getattr__
    if view is None:
        return services
    return replace(services, secom=view(services.secom, position))


def services_whole_line(services: ScienceServices) -> ScienceServices:
    """The services with every SECOM unit visible: a run's real units were chosen from the
    whole dataset, so none of them is still "on the line" for the run's investigation or chat."""
    timeline = getattr(services.secom, "timeline", None)
    if timeline is None:
        return services
    return services_as_of(services, len(timeline) - 1)


def _services(ctx: GraphContext, state: InvestigationState) -> ScienceServices:
    as_of = state.get("as_of")
    if as_of is None and state["trigger"].get("kind") == "run_alarm":
        return services_whole_line(ctx.services)
    return services_as_of(ctx.services, as_of)


def trigger_tools(trigger: InvestigationTrigger) -> tuple[ToolName, ...]:
    """The tools an investigation may call: every tool for an alarm raised in a run (the run
    tools, and the science tools for its real units and wafers), else the science tools."""
    return ALL_TOOL_NAMES if trigger.kind == "run_alarm" else SCIENCE_TOOL_NAMES


async def knowledge_source_ids(services: ScienceServices) -> frozenset[str] | None:
    """Every source ID of the knowledge base, or None when it cannot be read."""
    try:
        causes = await services.knowledge.pattern_causes()
    except ServiceError:
        return None
    return frozenset(source.source_id for source in causes.sources)


@dataclass(frozen=True, slots=True)
class GraphContext:
    """What the nodes use; passed on each run, never stored in a checkpoint."""

    gateway: LlmGateway
    services: ScienceServices
    sink: InvestigationSink
    writer: ReportWriter
    verifier: ReportVerifier
    limits: InvestigationLimits
    wall_clock: Callable[[], datetime]


@dataclass
class _Step:
    """One investigation step, sent to the sink when it starts and again when it ends."""

    ctx: GraphContext
    investigation_id: str
    index: int
    node: GraphNode
    title: str
    tool: ToolName | None = None
    started_at: datetime | None = None
    records: list[LlmCallRecord] = field(default_factory=list)

    def options(self) -> CallOptions:
        return CallOptions(correlation_id=self.investigation_id, on_record=self.records.append)

    def model(
        self, status: StepStatus, evidence_ids: Sequence[str] = (), *, finished: bool = False
    ) -> InvestigationStep:
        started = self.started_at or self.ctx.wall_clock()
        return InvestigationStep(
            index=self.index,
            node=self.node,
            status=status,
            title=self.title,
            started_at=started,
            finished_at=self.ctx.wall_clock() if finished else None,
            tool=self.tool,
            evidence_ids=list(evidence_ids),
            llm=[to_call_usage(r) for r in self.records if r.sent or r.cache_hit],
        )

    async def start(self) -> None:
        self.started_at = self.ctx.wall_clock()
        await self.ctx.sink.step(self.model("running"))

    async def end(self, status: StepStatus, evidence_ids: Sequence[str] = ()) -> None:
        await self.ctx.sink.step(self.model(status, evidence_ids, finished=True))


def llm_problem(exc: LlmError) -> Problem:
    retry_after = None
    if isinstance(exc, TokenFactoryHttpError) and exc.retry_after is not None:
        retry_after = max(round(exc.retry_after), 0)
    title = "No model available" if isinstance(exc, NoModelAvailableError) else "Model error"
    return Problem(
        title=title,
        status=502,
        detail=f"{type(exc).__name__}: {exc}"[:600],
        code="upstream_error",
        retry_after_s=retry_after,
    )


def triage_call(trigger: InvestigationTrigger) -> tuple[ToolName, dict[str, Any]] | None:
    """The first, deterministic tool call for a trigger (None when the trigger names nothing
    a tool can read)."""
    ref = trigger.ref.strip()
    if trigger.kind == "run_alarm":
        parsed = parse_run_alarm_ref(ref)
        return ("get_run", {"run_id": parsed[0]}) if parsed else None
    if trigger.kind == "unit":
        return ("get_unit", {"unit_id": int(ref)}) if ref.isdigit() else None
    if trigger.kind == "alarm":
        match = _ALARM.match(ref)
        return ("get_unit", {"unit_id": int(match.group("unit"))}) if match else None
    if trigger.kind == "wafer":
        return "get_wafer_prediction", {"wafer_id": ref}
    return "get_lot_stats", {"lot": ref}


def _evidence(state: InvestigationState) -> list[Evidence]:
    return [Evidence.model_validate(item) for item in state["evidence"]]


def _dump(message: ChatMessage) -> dict[str, Any]:
    return message.model_dump(mode="json", exclude_none=True)


def plan_request(state: InvestigationState, limits: InvestigationLimits) -> ChatRequest:
    system = ChatMessage.system(INVESTIGATOR_SYSTEM.format(max_tool_steps=limits.max_tool_steps))
    history = tuple(ChatMessage.model_validate(m) for m in state["messages"])
    trigger = InvestigationTrigger.model_validate(state["trigger"])
    return ChatRequest(
        messages=(system, *history),
        max_tokens=limits.plan_max_tokens,
        tools=tool_specs(trigger_tools(trigger)),
        tool_choice="auto",
    )


def _tool_message(call_id: str, outcome: ToolOutcome) -> dict[str, Any]:
    return _dump(ChatMessage.tool(call_id, outcome.message_for_model()))


async def _record_outcome(ctx: GraphContext, step: _Step, outcome: ToolOutcome) -> None:
    if outcome.status == "new" and outcome.evidence is not None:
        await ctx.sink.evidence(outcome.evidence)
    if outcome.evidence is not None:
        await step.end("completed", [outcome.evidence.evidence_id])
    else:
        await step.end("failed")


# -- nodes ------------------------------------------------------------------------------------


def _invalid_trigger(detail: str | None) -> dict[str, Any]:
    return Problem(
        title="Invalid trigger", status=400, detail=detail, code="bad_request"
    ).model_dump(mode="json")


async def _triage_step(
    ctx: GraphContext,
    executor: ToolExecutor,
    investigation_id: str,
    index: int,
    call: tuple[ToolName, dict[str, Any]],
) -> ToolOutcome:
    prepared = executor.prepare(*call)
    step = _Step(ctx, investigation_id, index, "triage", prepared.title, prepared.tool.name if prepared.tool else None)  # fmt: skip
    await step.start()
    outcome = await executor.run(prepared)
    await _record_outcome(ctx, step, outcome)
    return outcome


async def _alarm_item(
    services: ScienceServices, trigger: InvestigationTrigger
) -> tuple[ToolName, dict[str, Any]] | Problem | None:
    """The run tool call for the item a run alarm is about; a problem when the alarm is not
    part of the run; None when the alarm names no single item."""
    parsed = parse_run_alarm_ref(trigger.ref)
    if parsed is None:
        return None
    run_id, alarm_id = parsed
    try:
        run = await read_run(services, run_id)
    except ServiceError as exc:
        return exc.problem()
    if not any(a.alarm_id == alarm_id for a in run.alarms):
        return Problem(
            title="Alarm not found",
            status=404,
            detail=f"run {run_id} has no alarm {alarm_id}",
            code="not_found",
        )
    call = alarm_item_call(run, alarm_id)
    return (call[0], dict(call[1])) if call else None


async def triage(state: InvestigationState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    ctx = runtime.context
    trigger = InvestigationTrigger.model_validate(state["trigger"])
    investigation_id = state["investigation_id"]
    services = _services(ctx, state)
    ledger = EvidenceLedger(investigation_id)
    executor = ToolExecutor(
        services, ledger, wall_clock=ctx.wall_clock, allowed=trigger_tools(trigger)
    )
    chosen = triage_call(trigger)
    if chosen is None:
        detail = f"the {trigger.kind} reference does not name anything a tool can read"
        return {"failure": _invalid_trigger(detail)}
    index = state["next_step"]
    outcome = await _triage_step(ctx, executor, investigation_id, index, chosen)
    update: dict[str, Any] = {"next_step": index + 1, "tool_steps": 1}
    if outcome.evidence is None:
        problem = outcome.problem
        update["failure"] = (
            problem.model_dump(mode="json") if problem else _invalid_trigger(outcome.error)
        )
        return update
    gathered = [outcome.evidence]
    if trigger.kind == "run_alarm":
        item = await _alarm_item(services, trigger)
        if isinstance(item, Problem):
            update["failure"] = item.model_dump(mode="json")
            return update
        if item is not None:
            second = await _triage_step(ctx, executor, investigation_id, index + 1, item)
            update["next_step"] = index + 2
            update["tool_steps"] = 2
            if second.evidence is not None:
                gathered.append(second.evidence)
    first = data_message(
        {
            "trigger": trigger.model_dump(mode="json"),
            "evidence": [model_view(e) for e in gathered],
            "tool_calls_used": update["tool_steps"],
        }
    )
    update["evidence"] = [e.model_dump(mode="json") for e in ledger.items]
    update["messages"] = [_dump(ChatMessage.user(first))]
    return update


async def plan(state: InvestigationState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    ctx = runtime.context
    limits = ctx.limits
    used = state["tool_steps"]
    title = f"Choose the next evidence ({used} of {limits.max_tool_steps} tool calls used)"
    step = _Step(ctx, state["investigation_id"], state["next_step"], "plan", title)
    await step.start()
    update: dict[str, Any] = {"next_step": state["next_step"] + 1}
    try:
        result = await ctx.gateway.complete(
            Role.INVESTIGATOR, plan_request(state, limits), options=step.options()
        )
    except LlmError as exc:
        await step.end("failed")
        update["failure"] = llm_problem(exc).model_dump(mode="json")
        return update
    await step.end("completed")
    calls = [
        {"id": call.id, "name": call.function.name, "arguments": call.function.arguments}
        for call in result.tool_calls
    ]
    update["pending"] = calls
    if calls:
        assistant = ChatMessage.assistant(result.content or None, result.tool_calls)
        update["messages"] = [*state["messages"], _dump(assistant)]
    return update


async def gather(state: InvestigationState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    ctx = runtime.context
    limit = ctx.limits.max_tool_steps
    investigation_id = state["investigation_id"]
    ledger = EvidenceLedger(investigation_id, _evidence(state))
    trigger = InvestigationTrigger.model_validate(state["trigger"])
    executor = ToolExecutor(
        _services(ctx, state), ledger, wall_clock=ctx.wall_clock, allowed=trigger_tools(trigger)
    )
    used = state["tool_steps"]
    index = state["next_step"]
    messages = list(state["messages"])
    for position, call in enumerate(state["pending"]):
        call_id = str(call["id"]) or f"call_{index}_{position}"
        prepared = executor.prepare(str(call["name"]), call["arguments"])
        tool = prepared.tool.name if prepared.tool else None
        if used >= limit:
            skipped = _Step(ctx, investigation_id, index, "evidence", prepared.title, tool)
            skipped.started_at = ctx.wall_clock()
            await ctx.sink.step(skipped.model("skipped", finished=True))
            index += 1
            refusal = f"not run: the investigation's limit of {limit} tool calls is reached"
            messages.append(_dump(ChatMessage.tool(call_id, data_json({"error": refusal}))))
            continue
        step = _Step(ctx, investigation_id, index, "evidence", prepared.title, tool)
        await step.start()
        outcome = await executor.run(prepared)
        used += 1
        index += 1
        await _record_outcome(ctx, step, outcome)
        messages.append(_tool_message(call_id, outcome))
    return {
        "evidence": [e.model_dump(mode="json") for e in ledger.items],
        "pending": [],
        "tool_steps": used,
        "next_step": index,
        "messages": messages,
    }


async def write(state: InvestigationState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    ctx = runtime.context
    revision = state["round"]
    title = (
        "Write the report"
        if revision == 0
        else f"Revise the report (revision {revision} of {ctx.limits.max_revisions})"
    )
    step = _Step(ctx, state["investigation_id"], state["next_step"], "write", title)
    await step.start()
    previous = Report.model_validate(state["report"]) if revision > 0 and state["report"] else None
    data = WriterInput(
        trigger=InvestigationTrigger.model_validate(state["trigger"]),
        evidence=_evidence(state),
        previous=previous,
        issues=[VerificationIssue.model_validate(i) for i in state["issues"]] if previous else [],
    )
    update: dict[str, Any] = {"next_step": state["next_step"] + 1}
    options = step.options()
    if revision > 0:
        # A revision must reach the model: an identical request (same draft, same problems)
        # would otherwise be answered from the cache with the same failing draft.
        options = replace(options, use_cache=False)
    try:
        out = await ctx.writer.write(data, options=options)
    except LlmError as exc:
        await step.end("failed")
        update["failure"] = llm_problem(exc).model_dump(mode="json")
        return update
    await step.end("completed")
    update["report"] = out.value.model_dump(mode="json")
    update["writer_model"] = out.result.model
    return update


async def verify(state: InvestigationState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    ctx = runtime.context
    revision = state["round"]
    title = "Send the report (not checked)"
    step = _Step(ctx, state["investigation_id"], state["next_step"], "verify", title)
    await step.start()
    report = Report.model_validate(state["report"])
    # Single pass (owner's choice, 2026-10-16): no code checks, no verifier model, no
    # revisions. The report goes to the engineer as the writer wrote it.
    verification = Verification(
        passed=True,
        rounds=0,
        numbers_checked=0,
        numbers_matched=0,
        issues=[],
        claims=[
            ClaimVerdict(finding_index=i, verdict="not_checked", note=None)
            for i in range(len(report.findings))
        ],
        verifier_model=None,
    )
    await step.end("completed")
    await ctx.sink.report(report, round=revision)
    await ctx.sink.verification(verification, round=revision)
    revise = False
    update: dict[str, Any] = {
        "next_step": state["next_step"] + 1,
        "verification": verification.model_dump(mode="json"),
        "revise": revise,
    }
    if revise:
        update["round"] = revision + 1
        update["issues"] = [
            i.model_dump(mode="json") for i in verification.issues if i.severity == "error"
        ]
    return update


async def await_decision(
    state: InvestigationState, runtime: Runtime[GraphContext]
) -> dict[str, Any]:
    ctx = runtime.context
    index = state["next_step"]
    step = _Step(ctx, state["investigation_id"], index, "decision", "Wait for the engineer's decision")  # fmt: skip
    await step.start()
    await ctx.sink.status("awaiting_decision")
    started = step.started_at or ctx.wall_clock()
    return {
        "next_step": index + 1,
        "decision_step": {"index": index, "started_at": started.isoformat()},
    }


async def decision(state: InvestigationState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    value = interrupt({"investigation_id": state["investigation_id"], "waiting_for": "decision"})
    ctx = runtime.context
    decided = Decision.model_validate(value)
    record = state["decision_step"] or {"index": state["next_step"], "started_at": None}
    step = _Step(ctx, state["investigation_id"], int(record["index"]), "decision", "Wait for the engineer's decision")  # fmt: skip
    if record["started_at"]:
        step.started_at = datetime.fromisoformat(str(record["started_at"]))
    await step.end("completed")
    # The API is the single source of the approved and rejected statuses: the graph only
    # records the decision.
    return {"decision": decided.model_dump(mode="json")}


# -- edges ------------------------------------------------------------------------------------


def _after_plan(state: InvestigationState) -> Literal["evidence", "write", "__end__"]:
    if state["failure"]:
        return "__end__"
    return "evidence" if state["pending"] else "write"


def _after_write(state: InvestigationState) -> Literal["verify", "__end__"]:
    return "__end__" if state["failure"] else "verify"


def _after_verify(state: InvestigationState) -> Literal["write", "await_decision"]:
    return "write" if state["revise"] else "await_decision"


def build_graph(limits: InvestigationLimits) -> StateGraph[InvestigationState, GraphContext]:
    def after_triage(state: InvestigationState) -> Literal["plan", "write", "__end__"]:
        if state["failure"]:
            return "__end__"
        return "plan" if state["tool_steps"] < limits.max_tool_steps else "write"

    def after_evidence(state: InvestigationState) -> Literal["plan", "write"]:
        return "plan" if state["tool_steps"] < limits.max_tool_steps else "write"

    graph = StateGraph(InvestigationState, context_schema=GraphContext)
    graph.add_node("triage", triage)
    graph.add_node("plan", plan)
    graph.add_node("evidence", gather)
    graph.add_node("write", write)
    graph.add_node("verify", verify)
    graph.add_node("await_decision", await_decision)
    graph.add_node("decision", decision)
    graph.add_edge(START, "triage")
    graph.add_conditional_edges("triage", after_triage)
    graph.add_conditional_edges("plan", _after_plan)
    graph.add_conditional_edges("evidence", after_evidence)
    graph.add_conditional_edges("write", _after_write)
    graph.add_conditional_edges("verify", _after_verify)
    graph.add_edge("await_decision", "decision")
    graph.add_edge("decision", END)
    return graph


# -- runner -----------------------------------------------------------------------------------


def _conflict(detail: str) -> Problem:
    return Problem(title="Conflict", status=409, detail=detail, code="conflict")


class InvestigatorRunner:
    """Implements :class:`~yield_guardian.contracts.services.InvestigationRunner`."""

    def __init__(
        self,
        *,
        gateway: LlmGateway,
        services: ScienceServices,
        checkpointer: BaseCheckpointSaver[Any],
        limits: InvestigationLimits | None = None,
        writer: ReportWriter | None = None,
        verifier: ReportVerifier | None = None,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.gateway = gateway
        self.services = services
        self.limits = limits or InvestigationLimits()
        self.writer = writer or ReportWriter(gateway, max_tokens=self.limits.writer_max_tokens)
        self.verifier = verifier or ReportVerifier(gateway)
        self.wall_clock = wall_clock
        self.graph = build_graph(self.limits).compile(checkpointer=checkpointer)

    def _context(self, sink: InvestigationSink) -> GraphContext:
        return GraphContext(
            gateway=self.gateway,
            services=self.services,
            sink=sink,
            writer=self.writer,
            verifier=self.verifier,
            limits=self.limits,
            wall_clock=self.wall_clock,
        )

    @staticmethod
    def config(investigation_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": investigation_id}}

    async def waiting_for_decision(self, investigation_id: str) -> bool:
        snapshot = await self.graph.aget_state(self.config(investigation_id))
        return "decision" in snapshot.next

    async def run(
        self,
        investigation_id: str,
        trigger: InvestigationTrigger,
        sink: InvestigationSink,
        *,
        as_of: int | None = None,
    ) -> None:
        snapshot = await self.graph.aget_state(self.config(investigation_id))
        if snapshot.values:
            await sink.error(_conflict(f"investigation {investigation_id} has already run"))
            return
        await sink.status("running")
        state = initial_state(investigation_id, trigger, as_of=as_of)
        await self._drive(state, investigation_id, sink)

    async def resume(
        self, investigation_id: str, decision: Decision, sink: InvestigationSink
    ) -> None:
        if not await self.waiting_for_decision(investigation_id):
            await sink.error(
                _conflict(f"investigation {investigation_id} is not waiting for a decision")
            )
            return
        await self._drive(Command(resume=decision.model_dump(mode="json")), investigation_id, sink)

    async def _drive(
        self,
        graph_input: InvestigationState | Command[Any],
        investigation_id: str,
        sink: InvestigationSink,
    ) -> None:
        try:
            values = await self.graph.ainvoke(
                graph_input, self.config(investigation_id), context=self._context(sink)
            )
        except Exception as exc:
            log.exception("investigation_failed", investigation_id=investigation_id)
            problem = Problem(
                title="Investigation failed",
                status=500,
                detail=f"an internal error stopped the investigation ({type(exc).__name__})",
                code="internal_error",
            )
            await sink.error(problem)
            await sink.status("failed")
            return
        failure = values.get("failure") if isinstance(values, dict) else None
        if failure:
            await sink.error(Problem.model_validate(failure))
            await sink.status("failed")


# -- recorded runs ------------------------------------------------------------------------------


def _thread(investigation_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": investigation_id}}


async def paused_values(
    checkpointer: BaseCheckpointSaver[Any], investigation_id: str
) -> dict[str, Any] | None:
    """The state of a run paused for the engineer's decision (JSON only), or None."""
    graph = build_graph(InvestigationLimits()).compile(checkpointer=checkpointer)
    snapshot = await graph.aget_state(_thread(investigation_id))
    if "decision" not in snapshot.next or not snapshot.values:
        return None
    return dict(snapshot.values)


async def restore_paused(
    checkpointer: BaseCheckpointSaver[Any], investigation_id: str, values: dict[str, Any]
) -> bool:
    """Recreate a run paused for the decision from its saved state, so a recorded run imported on
    another host can still be decided. No node that calls a model runs: the state is written as
    the output of ``await_decision``, then the ``decision`` node runs up to its interrupt.
    Returns False when the thread already has a state (nothing is changed)."""
    graph = build_graph(InvestigationLimits()).compile(checkpointer=checkpointer)
    config = _thread(investigation_id)
    if (await graph.aget_state(config)).values:
        return False
    if values.get("investigation_id") != investigation_id:
        raise ValueError("the saved state belongs to another investigation")
    config = await graph.aupdate_state(config, values, as_node="await_decision")
    await graph.ainvoke(None, config)
    if "decision" not in (await graph.aget_state(_thread(investigation_id))).next:
        raise RuntimeError("the restored run is not waiting for a decision")
    return True
