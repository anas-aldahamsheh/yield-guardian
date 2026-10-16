"""The investigator's and the chat's tools: typed, read-only, each result stored as evidence.

Each of the eleven science tools (PLAN 7.3) wraps one read method of the science services; the
four run tools (:mod:`yield_guardian.agent.run_tools`) read one run (PLAN_V2 3.4). A call is
validated against a Pydantic argument model with tight bounds, executed, and stored as an
:class:`~yield_guardian.contracts.investigation.Evidence` record with a stable ID (``E1``,
``E2`` ...) and a one-line summary written by code. The same call twice returns the same
evidence. There is no tool that writes anything: the model can read and recommend, never act.

What the model sees of a result is a projection of ``Evidence.data`` that drops bulky fields
(wafer-map pixels, stacked-map frequencies) but never renames or re-indexes anything, so every
JSON Pointer the model writes into its report resolves in the stored evidence.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, ValidationError, model_validator

from yield_guardian.agent.prompts import data_json
from yield_guardian.agent.run_tools import RUN_TOOLS
from yield_guardian.agent.tool_base import Tool
from yield_guardian.agent.tool_base import ToolArgs as _Args
from yield_guardian.contracts.base import (
    BundleRef,
    LotId,
    Problem,
    SensorId,
    SequenceNo,
    UnitId,
    WaferId,
)
from yield_guardian.contracts.investigation import Evidence, ToolName
from yield_guardian.contracts.knowledge import KnowledgeSearchResult
from yield_guardian.contracts.secom import (
    Explanation,
    FdcContributions,
    FdcSeries,
    FdcStatistic,
    SensorGroups,
    SensorHealthReport,
    SensorStatus,
    UnitDetail,
    UnitRisk,
)
from yield_guardian.contracts.services import ScienceServices, ServiceError
from yield_guardian.contracts.wafer import LotDetail, SimilarWafers, WaferPrediction
from yield_guardian.llm.cache import canonical_json
from yield_guardian.llm.messages import ToolSpec

MAX_FDC_WINDOW = 40
"""Units per FDC window: enough to see a drift, small enough for the model's context."""

ALL_TOOL_NAMES: tuple[ToolName, ...] = get_args(ToolName)


class UnitArgs(_Args):
    unit_id: UnitId


class ShapArgs(_Args):
    unit_id: UnitId
    top_k: int = Field(10, ge=1, le=30, description="Number of largest contributions to return.")


class FeatureGroupArgs(_Args):
    significant_only: bool = Field(
        True, description="Only groups whose association with failure is significant."
    )
    limit: int = Field(10, ge=1, le=20, description="Number of groups to return.")


class FdcWindowArgs(_Args):
    from_seq: SequenceNo
    to_seq: SequenceNo

    @model_validator(mode="after")
    def _window(self) -> FdcWindowArgs:
        if self.to_seq < self.from_seq:
            raise ValueError("to_seq must not be before from_seq")
        if self.to_seq - self.from_seq >= MAX_FDC_WINDOW:
            raise ValueError(f"a window holds at most {MAX_FDC_WINDOW} units")
        return self


class ContributionArgs(_Args):
    unit_id: UnitId
    statistic: FdcStatistic = Field("t2", description="t2 (Hotelling T²) or spe (Q residual).")
    top_k: int = Field(10, ge=1, le=30, description="Number of largest contributions to return.")


class SensorHealthArgs(_Args):
    sensors: list[SensorId] | None = Field(None, min_length=1, max_length=20)
    statuses: list[SensorStatus] | None = Field(None, min_length=1, max_length=4)

    @model_validator(mode="after")
    def _filter(self) -> SensorHealthArgs:
        if self.sensors is None and self.statuses is None:
            raise ValueError("give sensors, statuses or both")
        if self.sensors is not None and len(set(self.sensors)) != len(self.sensors):
            raise ValueError("sensors must not repeat")
        return self


class WaferArgs(_Args):
    wafer_id: WaferId


class SimilarArgs(_Args):
    wafer_id: WaferId
    k: int = Field(5, ge=1, le=10, description="Number of similar wafers to return.")


class LotArgs(_Args):
    lot: LotId


class KnowledgeArgs(_Args):
    query: str = Field(min_length=2, max_length=200, description="Words to search for.")
    limit: int = Field(5, ge=1, le=8, description="Number of passages to return.")


def _num(value: float | None, digits: int = 3) -> str:
    return "not available" if value is None else f"{value:.{digits}g}"


def _statistic_name(statistic: FdcStatistic) -> str:
    return "T²" if statistic == "t2" else "SPE"


def _unit_summary(args: UnitArgs, u: UnitDetail) -> str:
    risk = "not available" if u.risk is None else f"{u.risk:.3f} ({u.risk_band})"
    final = u.final_test or "not revealed yet"
    return (
        f"Unit {u.unit_id} at sequence {u.sequence} ({u.block} block): risk {risk}, "
        f"T² {_num(u.t2)}, SPE {_num(u.spe)}, FDC level {u.fdc_alarm}, {len(u.alarms)} alarms, "
        f"final test {final}."
    )


def _risk_summary(args: UnitArgs, r: UnitRisk) -> str:
    if r.risk is None:
        return f"Unit {r.unit_id}: no calibrated risk ({r.note or 'not available'})."
    side = "above" if r.above_threshold else "below"
    return (
        f"Unit {r.unit_id}: calibrated risk {r.risk:.3f} ({r.risk_band}), {side} the threshold "
        f"{r.operating_point.threshold:.3f} of the operating point '{r.operating_point.label}'."
    )


def _shap_summary(args: ShapArgs, e: Explanation) -> str:
    if not e.contributions:
        return f"Unit {e.unit_id}: no SHAP contributions listed."
    top = e.contributions[0]
    return (
        f"Unit {e.unit_id}: largest SHAP contribution {top.feature} {top.shap:+.3f} log-odds; "
        f"{len(e.contributions)} contributions and {len(e.groups)} sensor groups listed."
    )


def _groups_summary(args: FeatureGroupArgs, g: SensorGroups) -> str:
    return (
        f"{g.significant_groups} significant sensor groups covering "
        f"{g.sensors_in_significant_groups} of {g.sensors_total} sensors; "
        f"{len(g.groups)} groups listed."
    )


def _fdc_summary(args: FdcWindowArgs, s: FdcSeries) -> str:
    alarms = sum(p.fdc_alarm == "alarm" for p in s.points)
    warnings = sum(p.fdc_alarm == "warning" for p in s.points)
    return (
        f"FDC points for sequences {args.from_seq} to {args.to_seq}: {len(s.points)} units, "
        f"{alarms} at alarm level and {warnings} at warning level."
    )


def _contributions_summary(args: ContributionArgs, c: FdcContributions) -> str:
    head = (
        f"Unit {c.unit_id}: {_statistic_name(c.statistic)} {_num(c.value)} "
        f"(99% limit {_num(c.limit_99)}, 99.9% limit {_num(c.limit_999)}, level {c.alarm})"
    )
    if not c.contributions:
        return head + "."
    top = c.contributions[0]
    return f"{head}; largest contribution {top.sensor}, share {top.share:.1%}."


def _health_summary(args: SensorHealthArgs, h: SensorHealthReport) -> str:
    by_status: dict[str, int] = {}
    for sensor in h.sensors:
        by_status[sensor.status] = by_status.get(sensor.status, 0) + 1
    counts = ", ".join(f"{n} {status}" for status, n in sorted(by_status.items())) or "none"
    return f"Sensor health of {len(h.sensors)} sensors: {counts}."


def _prediction_summary(args: WaferArgs, p: WaferPrediction) -> str:
    kind = "unknown pattern" if p.unknown.is_unknown else "known pattern"
    return (
        f"Wafer {p.wafer_id}: predicted {p.top_label} with probability "
        f"{p.top_probability:.3f}; {kind} (Mahalanobis score {_num(p.unknown.score)}, threshold "
        f"{_num(p.unknown.threshold)} set on {p.unknown.threshold_set_on})."
    )


def _similar_summary(args: SimilarArgs, s: SimilarWafers) -> str:
    if not s.results:
        return f"No similar wafers found for {s.wafer_id}."
    return (
        f"{len(s.results)} wafers most similar to {s.wafer_id}; highest cosine similarity "
        f"{s.results[0].similarity:.3f}."
    )


def _lot_summary(args: LotArgs, d: LotDetail) -> str:
    flagged = [t.label for t in d.tests if t.flagged]
    return (
        f"Lot {d.lot}: {len(d.wafers)} wafers; patterns flagged against the training-period "
        f"rate: {', '.join(flagged) or 'none'}."
    )


def _knowledge_summary(args: KnowledgeArgs, k: KnowledgeSearchResult) -> str:
    return f"{len(k.hits)} passages found for the query {args.query!r}."


def _sensor_health_title(a: SensorHealthArgs) -> str:
    if a.sensors:
        return f"Read the health of sensors {', '.join(a.sensors)}"
    return f"List sensors with status {', '.join(a.statuses or [])}"


_SCIENCE_TOOLS: Mapping[ToolName, Tool[Any, Any]] = {
    tool.name: tool
    for tool in (
        Tool(
            "get_unit",
            "Read one production unit: time, risk, T², SPE, alarms, final test if revealed.",
            UnitArgs,
            lambda s, a: s.secom.get_unit(a.unit_id),
            lambda a: f"Read unit {a.unit_id}",
            _unit_summary,
        ),
        Tool(
            "get_risk",
            "Read the calibrated failure risk of a unit and the operating point it is judged at.",
            UnitArgs,
            lambda s, a: s.secom.get_risk(a.unit_id),
            lambda a: f"Read the risk of unit {a.unit_id}",
            _risk_summary,
        ),
        Tool(
            "get_shap",
            "Read the TreeSHAP explanation of a unit's risk score (log-odds), by sensor and group.",
            ShapArgs,
            lambda s, a: s.secom.get_explanation(a.unit_id, top_k=a.top_k),
            lambda a: f"Read the SHAP explanation of unit {a.unit_id}",
            _shap_summary,
        ),
        Tool(
            "get_feature_groups",
            "Read the groups of correlated sensors associated with failure across all units, "
            "with stability and permutation-test results.",
            FeatureGroupArgs,
            lambda s, a: s.secom.get_feature_groups(
                significant_only=a.significant_only, limit=a.limit
            ),
            lambda a: "Read the sensor groups associated with failure",
            _groups_summary,
        ),
        Tool(
            "get_fdc_window",
            f"Read multivariate control-chart points (T², SPE, EWMA, CUSUM) for a window of at "
            f"most {MAX_FDC_WINDOW} units, by sequence number.",
            FdcWindowArgs,
            lambda s, a: s.secom.get_fdc_series(from_seq=a.from_seq, to_seq=a.to_seq),
            lambda a: f"Read FDC points for sequences {a.from_seq} to {a.to_seq}",
            _fdc_summary,
            hidden=("/points/*/timestamp", "/points/*/fdc_period"),
        ),
        Tool(
            "get_contributions",
            "Read which sensors contribute most to a unit's T² or SPE statistic.",
            ContributionArgs,
            lambda s, a: s.secom.get_contributions(a.unit_id, statistic=a.statistic, top_k=a.top_k),
            lambda a: f"Read the {_statistic_name(a.statistic)} contributions of unit {a.unit_id}",
            _contributions_summary,
        ),
        Tool(
            "get_sensor_health",
            "Read the health of sensors (status ok, watch, maintenance or dead, with the rules "
            "that set it: missing data, flat lines, stuck values, jumps), by sensor IDs or by "
            "status.",
            SensorHealthArgs,
            lambda s, a: s.secom.get_sensor_health(sensors=a.sensors, statuses=a.statuses),
            _sensor_health_title,
            _health_summary,
        ),
        Tool(
            "get_wafer_prediction",
            "Read the defect-pattern prediction of a wafer map, with the unknown-pattern score.",
            WaferArgs,
            lambda s, a: s.wafer.get_prediction(a.wafer_id),
            lambda a: f"Read the pattern prediction of wafer {a.wafer_id}",
            _prediction_summary,
        ),
        Tool(
            "get_similar_wafers",
            "Find the wafers whose maps are most similar to a wafer (CNN embeddings).",
            SimilarArgs,
            lambda s, a: s.wafer.get_similar(a.wafer_id, k=a.k),
            lambda a: f"Find wafers similar to {a.wafer_id}",
            _similar_summary,
            hidden=("/results/*/map",),
            caps=(("/results", 5),),
        ),
        Tool(
            "get_lot_stats",
            "Read a lot's wafers and its pattern-excursion tests against the training-period rate.",
            LotArgs,
            lambda s, a: s.wafer.get_lot(a.lot),
            lambda a: f"Read the pattern tests of lot {a.lot}",
            _lot_summary,
            hidden=("/stacked",),
            caps=(("/wafers", 12),),
        ),
        Tool(
            "search_knowledge",
            "Search curated open-access literature on wafer defect patterns (full-text search).",
            KnowledgeArgs,
            lambda s, a: s.knowledge.search(a.query, limit=a.limit),
            lambda a: f"Search the literature for {a.query!r}",
            _knowledge_summary,
        ),
    )
}
TOOLS: Mapping[ToolName, Tool[Any, Any]] = {
    **_SCIENCE_TOOLS,
    **{tool.name: tool for tool in RUN_TOOLS},
}
SCIENCE_TOOL_NAMES: tuple[ToolName, ...] = tuple(_SCIENCE_TOOLS)
"""The tools over the SECOM, WM-811K and literature bundles (every tool but the run tools)."""


def tool_specs(names: Iterable[ToolName] = ALL_TOOL_NAMES) -> tuple[ToolSpec, ...]:
    return tuple(TOOLS[name].spec() for name in names)


def _drop(data: Any, pattern: Sequence[str]) -> Any:
    """Remove the object members matched by ``pattern`` (tokens; ``*`` matches any key or
    index). List items are never removed, so indexes stay as in the stored evidence."""
    head, rest = pattern[0], pattern[1:]
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if head not in ("*", key):
                out[key] = value
            elif rest:
                out[key] = _drop(value, rest)
        return out
    if isinstance(data, list) and rest:
        return [
            _drop(item, rest) if head in ("*", str(index)) else item
            for index, item in enumerate(data)
        ]
    return data


def _cap(data: Any, pattern: Sequence[str], limit: int, path: str, cut: dict[str, int]) -> Any:
    """Cut the lists matched by ``pattern`` to their first ``limit`` items; ``cut`` gets the
    full length of each list cut, by its path."""
    if not pattern:
        if isinstance(data, list) and len(data) > limit:
            cut[path or "/"] = len(data)
            return data[:limit]
        return data
    head, rest = pattern[0], pattern[1:]
    if isinstance(data, dict):
        return {
            k: _cap(v, rest, limit, f"{path}/{k}", cut) if head in ("*", k) else v
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [
            _cap(v, rest, limit, f"{path}/{i}", cut) if head in ("*", str(i)) else v
            for i, v in enumerate(data)
        ]
    return data


VIEW_DIGITS = 4
"""Significant digits of a decimal in the model's view. A number the writer copies from it still
matches the stored value (:mod:`yield_guardian.agent.numbers` allows half a unit in the last
written digit)."""


def _rounded(data: Any) -> Any:
    if isinstance(data, float):
        return float(f"{data:.{VIEW_DIGITS}g}") if math.isfinite(data) else data
    if isinstance(data, dict):
        return {k: _rounded(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_rounded(v) for v in data]
    return data


def model_view(evidence: Evidence) -> dict[str, Any]:
    """What a language model is shown of one piece of evidence: the data without the parts a
    tool hides (maps, per-item lists, repeated text), long lists cut to their first items, and
    decimals at 4 significant digits. The stored evidence keeps everything."""
    tool = TOOLS[evidence.tool]
    data: Any = evidence.model_dump(mode="json")["data"]
    for pattern in tool.hidden:
        data = _drop(data, pattern.strip("/").split("/"))
    cut: dict[str, int] = {}
    for pattern, limit in tool.caps:
        data = _cap(data, pattern.strip("/").split("/"), limit, "", cut)
    view: dict[str, Any] = {
        "evidence_id": evidence.evidence_id,
        "tool": evidence.tool,
        "arguments": evidence.arguments,
        "summary": evidence.summary,
        "data": _rounded(data),
    }
    if tool.hidden:
        view["omitted_from_view"] = list(tool.hidden)
    if cut:
        view["lists_cut_in_view"] = {path: f"first of {n}" for path, n in cut.items()}
    return view


def view_json(evidence: Evidence) -> str:
    return data_json(model_view(evidence))


class EvidenceLedger:
    """Evidence of one investigation or one chat answer, with IDs E1, E2 ... in order."""

    def __init__(self, investigation_id: str | None, existing: Iterable[Evidence] = ()) -> None:
        self.investigation_id = investigation_id
        self._items: list[Evidence] = []
        self._by_call: dict[str, Evidence] = {}
        for item in existing:
            self._remember(item)

    @staticmethod
    def call_key(tool: str, arguments: Mapping[str, Any]) -> str:
        return canonical_json({"tool": tool, "arguments": arguments})

    def _remember(self, evidence: Evidence) -> None:
        self._items.append(evidence)
        self._by_call[self.call_key(evidence.tool, evidence.arguments)] = evidence

    @property
    def items(self) -> tuple[Evidence, ...]:
        return tuple(self._items)

    def ids(self) -> frozenset[str]:
        return frozenset(e.evidence_id for e in self._items)

    def get(self, evidence_id: str) -> Evidence | None:
        return next((e for e in self._items if e.evidence_id == evidence_id), None)

    def find(self, tool: str, arguments: Mapping[str, Any]) -> Evidence | None:
        return self._by_call.get(self.call_key(tool, arguments))

    def add(
        self,
        *,
        tool: ToolName,
        arguments: dict[str, Any],
        data: dict[str, Any],
        summary: str,
        created_at: datetime,
        source: BundleRef | None,
    ) -> Evidence:
        evidence = Evidence(
            evidence_id=f"E{len(self._items) + 1}",
            investigation_id=self.investigation_id,
            tool=tool,
            arguments=arguments,
            data=data,
            summary=summary,
            created_at=created_at,
            source=source,
        )
        self._remember(evidence)
        return evidence


OutcomeStatus = Literal["new", "reused", "invalid", "failed"]


@dataclass(frozen=True, slots=True)
class PreparedCall:
    """A requested tool call after validation, before it runs."""

    requested_name: str
    tool: Tool[Any, Any] | None
    args: _Args | None
    arguments: dict[str, Any] | None
    title: str
    error: str | None = None
    """Why the call is refused before running (unknown tool, invalid arguments)."""


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """The result of one requested tool call."""

    requested_name: str
    tool: ToolName | None
    status: OutcomeStatus
    title: str
    evidence: Evidence | None = None
    error: str | None = None
    problem: Problem | None = None
    """The service's problem details when the call failed in the service."""

    def message_for_model(self) -> str:
        """The tool message content: the evidence view, or the error, as JSON data."""
        if self.evidence is not None:
            return view_json(self.evidence)
        return data_json({"error": self.error})


def _bundle_of(result: BaseModel) -> BundleRef | None:
    for name in ("bundle", "model"):
        value = getattr(result, name, None)
        if isinstance(value, BundleRef):
            return value
    return None


def _arguments(raw: str | Mapping[str, Any] | None) -> Mapping[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, Mapping):
        return raw
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("the arguments must be a JSON object")
    return parsed


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", name)[:40] or "(no name)"


class ToolExecutor:
    """Runs tool calls against the science services and records the results as evidence."""

    def __init__(
        self,
        services: ScienceServices,
        ledger: EvidenceLedger,
        *,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        allowed: Iterable[ToolName] = ALL_TOOL_NAMES,
    ) -> None:
        self.services = services
        self.ledger = ledger
        self._wall_clock = wall_clock
        self._allowed = frozenset(allowed)

    def prepare(self, name: str, raw_arguments: str | Mapping[str, Any] | None) -> PreparedCall:
        """Validate a requested call: the tool must exist and the arguments must fit it."""
        if name not in self._allowed:
            return PreparedCall(
                name, None, None, None, f"Refused unknown tool {_safe_name(name)}",
                error=f"unknown tool {_safe_name(name)!r}; the available tools only read data: "
                + ", ".join(sorted(self._allowed)),
            )  # fmt: skip
        tool = TOOLS[name]
        try:
            args = tool.args.model_validate(_arguments(raw_arguments))
        except (ValueError, ValidationError) as exc:
            return PreparedCall(
                name, tool, None, None, f"Refused invalid arguments for {name}",
                error=_validation_text(exc),
            )  # fmt: skip
        return PreparedCall(name, tool, args, args.model_dump(mode="json"), tool.title(args))

    async def run(self, call: PreparedCall) -> ToolOutcome:
        """Run a prepared call; the same call twice returns the same evidence."""
        tool = call.tool
        if call.error is not None or tool is None or call.args is None or call.arguments is None:
            return ToolOutcome(
                call.requested_name,
                tool.name if tool else None,
                "invalid",
                call.title,
                error=call.error,
            )
        existing = self.ledger.find(tool.name, call.arguments)
        if existing is not None:
            return ToolOutcome(call.requested_name, tool.name, "reused", call.title, existing)
        try:
            result = await tool.call(self.services, call.args)
        except ServiceError as exc:
            return ToolOutcome(
                call.requested_name, tool.name, "failed", call.title,
                error=f"{exc.code}: {exc.detail}"[:500], problem=exc.problem(),
            )  # fmt: skip
        evidence = self.ledger.add(
            tool=tool.name,
            arguments=call.arguments,
            data=result.model_dump(mode="json"),
            summary=tool.summary(call.args, result),
            created_at=self._wall_clock(),
            source=_bundle_of(result),
        )
        return ToolOutcome(call.requested_name, tool.name, "new", call.title, evidence)

    async def execute(
        self, name: str, raw_arguments: str | Mapping[str, Any] | None
    ) -> ToolOutcome:
        return await self.run(self.prepare(name, raw_arguments))


def _validation_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "invalid arguments: " + "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(arguments)'}: {err['msg']}"
            for err in exc.errors()[:5]
        )
    return f"invalid arguments: {exc}"[:300]
