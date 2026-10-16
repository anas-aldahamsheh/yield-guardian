"""Test doubles for the agent: science services, a scripted model endpoint and a recording sink.

The science fakes serve the contract fixtures of ``packages/contracts/fixtures``. Their model
outputs (risk, SHAP, T², wafer predictions, knowledge passages) are placeholders: SYNTHETIC test
values, never shown to anyone. The scripted endpoint answers the gateway's HTTP requests with
replies written in each test; nothing reaches the network.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar, cast

import httpx
import respx
from pydantic import BaseModel

from tests.llm.helpers import HOST
from yield_guardian.agent.prompts import (
    CHAT_SYSTEM,
    INVESTIGATOR_SYSTEM,
    ROUTER_SYSTEM,
    VERIFIER_SYSTEM,
    WRITER_SYSTEM,
)
from yield_guardian.contracts.base import Problem
from yield_guardian.contracts.investigation import (
    Evidence,
    InvestigationStatus,
    InvestigationStep,
    Report,
    Verification,
)
from yield_guardian.contracts.knowledge import KnowledgeSearchResult, PatternCauses
from yield_guardian.contracts.secom import (
    Explanation,
    FdcContributions,
    FdcSeries,
    SensorGroups,
    SensorHealthReport,
    UnitDetail,
    UnitRisk,
)
from yield_guardian.contracts.services import (
    KnowledgeService,
    NotFoundError,
    ScienceServices,
    SecomService,
    WaferService,
)
from yield_guardian.contracts.wafer import LotDetail, SimilarWafers, WaferPrediction
from yield_guardian.live.protocols import RunReader

CONTRACT_FIXTURES = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "fixtures"
M = TypeVar("M", bound=BaseModel)


def fixture[M: BaseModel](name: str, model: type[M]) -> M:
    return model.model_validate_json((CONTRACT_FIXTURES / f"{name}.json").read_text())


class FakeSecom:
    """Serves the fixture unit (1062) and refuses every other unit, like the real service."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.unit = fixture("get_unit", UnitDetail)
        self.risk = fixture("get_unit_risk", UnitRisk)
        self.explanation = fixture("get_unit_explanation", Explanation)
        self.groups = fixture("get_sensor_groups", SensorGroups)
        self.fdc = fixture("get_fdc_series", FdcSeries)
        self.contributions = fixture("get_unit_contributions", FdcContributions)
        self.health = fixture("get_sensor_health", SensorHealthReport)

    def _known(self, unit_id: int) -> None:
        if unit_id != self.unit.unit_id:
            raise NotFoundError(f"unit {unit_id} does not exist")

    async def get_unit(self, unit_id: int) -> UnitDetail:
        self.calls.append(("get_unit", {"unit_id": unit_id}))
        self._known(unit_id)
        return self.unit

    async def get_risk(self, unit_id: int) -> UnitRisk:
        self.calls.append(("get_risk", {"unit_id": unit_id}))
        self._known(unit_id)
        return self.risk

    async def get_explanation(self, unit_id: int, *, top_k: int = 15) -> Explanation:
        self.calls.append(("get_explanation", {"unit_id": unit_id, "top_k": top_k}))
        self._known(unit_id)
        return self.explanation.model_copy(
            update={"contributions": self.explanation.contributions[:top_k]}
        )

    async def get_feature_groups(
        self, *, significant_only: bool = False, limit: int = 20
    ) -> SensorGroups:
        self.calls.append(("get_feature_groups", {"limit": limit}))
        return self.groups

    async def get_fdc_series(
        self, *, from_seq: int | None = None, to_seq: int | None = None
    ) -> FdcSeries:
        self.calls.append(("get_fdc_series", {"from_seq": from_seq, "to_seq": to_seq}))
        lo, hi = from_seq or 0, to_seq if to_seq is not None else 10**9
        points = [p for p in self.fdc.points if lo <= p.sequence <= hi]
        return self.fdc.model_copy(update={"points": points})

    async def get_contributions(
        self, unit_id: int, *, statistic: str = "t2", top_k: int = 10
    ) -> FdcContributions:
        self.calls.append(("get_contributions", {"unit_id": unit_id, "statistic": statistic}))
        self._known(unit_id)
        return self.contributions

    async def get_sensor_health(
        self, *, sensors: list[str] | None = None, statuses: list[str] | None = None
    ) -> SensorHealthReport:
        self.calls.append(("get_sensor_health", {"sensors": sensors, "statuses": statuses}))
        chosen = [
            s
            for s in self.health.sensors
            if (sensors is None or s.sensor in sensors)
            and (statuses is None or s.status in statuses)
        ]
        return self.health.model_copy(update={"sensors": chosen})


class FakeWafer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.prediction = fixture("get_wafer_prediction", WaferPrediction)
        self.similar = fixture("get_similar_wafers", SimilarWafers)
        self.lot = fixture("get_lot", LotDetail)

    async def get_prediction(self, wafer_id: str) -> WaferPrediction:
        self.calls.append(("get_prediction", {"wafer_id": wafer_id}))
        if wafer_id != self.prediction.wafer_id:
            raise NotFoundError(f"wafer {wafer_id} does not exist")
        return self.prediction

    async def get_similar(self, wafer_id: str, *, k: int = 10) -> SimilarWafers:
        self.calls.append(("get_similar", {"wafer_id": wafer_id, "k": k}))
        return self.similar.model_copy(update={"results": self.similar.results[:k]})

    async def get_lot(self, lot: str) -> LotDetail:
        self.calls.append(("get_lot", {"lot": lot}))
        if lot != self.lot.lot:
            raise NotFoundError(f"lot {lot} does not exist")
        return self.lot


class FakeKnowledge:
    def __init__(self, snippet: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.result = fixture("search_knowledge", KnowledgeSearchResult)
        if snippet is not None:
            hits = [h.model_copy(update={"snippet": snippet}) for h in self.result.hits]
            self.result = self.result.model_copy(update={"hits": hits})

    async def search(self, query: str, *, limit: int = 5) -> KnowledgeSearchResult:
        self.calls.append(("search", {"query": query, "limit": limit}))
        return self.result.model_copy(update={"query": query})

    async def pattern_causes(self, label: str | None = None) -> PatternCauses:
        return fixture("get_pattern_causes", PatternCauses)


@dataclass
class FakeScience:
    secom: FakeSecom = field(default_factory=FakeSecom)
    wafer: FakeWafer = field(default_factory=FakeWafer)
    knowledge: FakeKnowledge = field(default_factory=FakeKnowledge)
    runs: RunReader | None = None

    @property
    def services(self) -> ScienceServices:
        return ScienceServices(
            secom=cast(SecomService, self.secom),
            wafer=cast(WaferService, self.wafer),
            knowledge=cast(KnowledgeService, self.knowledge),
            runs=self.runs,
        )


# -- scripted model endpoint ------------------------------------------------------------------

_ROLES = {
    INVESTIGATOR_SYSTEM[:60]: "investigator",
    WRITER_SYSTEM[:60]: "writer",
    VERIFIER_SYSTEM[:60]: "verifier",
    CHAT_SYSTEM[:60]: "chat",
    ROUTER_SYSTEM[:60]: "router",
}
USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}


def _body(message: dict[str, Any], finish: str = "stop") -> dict[str, Any]:
    return {
        "id": "cmpl-test",
        "model": "scripted",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": USAGE,
    }


def text_reply(content: str) -> httpx.Response:
    return httpx.Response(200, json=_body({"role": "assistant", "content": content}))


def json_reply(payload: Any) -> httpx.Response:
    return text_reply(json.dumps(payload))


def tool_reply(*calls: tuple[str, dict[str, Any] | str]) -> httpx.Response:
    tool_calls = [
        {
            "id": f"call_{n}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": args if isinstance(args, str) else json.dumps(args),
            },
        }
        for n, (name, args) in enumerate(calls)
    ]
    message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
    return httpx.Response(200, json=_body(message, "tool_calls"))


def stream_reply(*pieces: str) -> httpx.Response:
    """A streamed answer: one content delta per piece, then a usage chunk and [DONE]."""
    chunks: list[dict[str, Any]] = [
        {
            "id": "cmpl-test",
            "model": "scripted",
            "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}],
        }
        for p in pieces
    ]
    chunks.append({"id": "cmpl-test", "model": "scripted", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": USAGE})  # fmt: skip
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


def error_reply(status: int, message: str = "scripted failure") -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": message}})


def role_of(body: dict[str, Any]) -> str:
    system = str(body["messages"][0].get("content") or "")
    for prefix, role in _ROLES.items():
        if system.startswith(prefix[:40]):
            return role
    raise AssertionError(f"unrecognised system prompt: {system[:80]!r}")


@dataclass
class ScriptedModel:
    """Answers each role's requests with the replies queued for it, in order; a queued
    exception (such as ``httpx.ReadTimeout``) is raised as the transport's failure."""

    queues: dict[str, list[httpx.Response | Exception]] = field(
        default_factory=lambda: defaultdict(list)
    )
    requests: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def add(self, role: str, *replies: httpx.Response | Exception) -> ScriptedModel:
        self.queues[role].extend(replies)
        return self

    def mount(self, router: respx.Router) -> ScriptedModel:
        router.route(host=HOST, path__regex=r"/chat/completions$").mock(side_effect=self)
        return self

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        role = role_of(body)
        self.requests.append((role, body))
        queue = self.queues[role]
        if not queue:
            raise AssertionError(f"no scripted reply left for the {role} role")
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def bodies(self, role: str) -> list[dict[str, Any]]:
        return [body for r, body in self.requests if r == role]

    def remaining(self) -> dict[str, int]:
        return {role: len(queue) for role, queue in self.queues.items() if queue}


# -- sink and clock -----------------------------------------------------------------------------


@dataclass
class RecordingSink:
    events: list[tuple[str, Any]] = field(default_factory=list)

    async def status(self, status: InvestigationStatus) -> None:
        self.events.append(("status", status))

    async def step(self, step: InvestigationStep) -> None:
        self.events.append(("step", step))

    async def evidence(self, evidence: Evidence) -> None:
        self.events.append(("evidence", evidence))

    async def report(self, report: Report, *, round: int) -> None:
        self.events.append(("report", (round, report)))

    async def verification(self, verification: Verification, *, round: int) -> None:
        self.events.append(("verification", (round, verification)))

    async def error(self, problem: Problem) -> None:
        self.events.append(("error", problem))

    def of(self, kind: str) -> list[Any]:
        return [payload for k, payload in self.events if k == kind]

    @property
    def statuses(self) -> list[str]:
        return [str(s) for s in self.of("status")]

    @property
    def steps(self) -> list[InvestigationStep]:
        return cast(list[InvestigationStep], self.of("step"))

    def final_steps(self) -> list[InvestigationStep]:
        """The last version of each step, by index."""
        latest: dict[int, InvestigationStep] = {}
        for step in self.steps:
            latest[step.index] = step
        return [latest[i] for i in sorted(latest)]


@dataclass
class TickingClock:
    """Wall clock that advances one second per reading, so step times are ordered."""

    now: datetime = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def evidence(
    evidence_id: str, data: dict[str, Any], *, tool: str = "get_unit", **arguments: Any
) -> Evidence:
    """A synthetic evidence record for unit tests (values are made up for the test)."""
    return Evidence.model_validate(
        {
            "evidence_id": evidence_id,
            "investigation_id": "inv_testcase01",
            "tool": tool,
            "arguments": arguments,
            "data": data,
            "summary": "synthetic test evidence",
            "created_at": "2026-10-14T12:00:00Z",
            "source": None,
        }
    )
