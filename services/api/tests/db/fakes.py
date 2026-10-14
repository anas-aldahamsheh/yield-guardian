"""A scripted investigator standing in for the LangGraph runner. Values are synthetic test data."""

import asyncio
from datetime import UTC, datetime
from typing import Literal

from yield_guardian.contracts.base import Problem
from yield_guardian.contracts.investigation import (
    Action,
    Decision,
    Evidence,
    Finding,
    InvestigationStep,
    InvestigationTrigger,
    NumberRef,
    Report,
    Verification,
)
from yield_guardian.contracts.models import CallUsage
from yield_guardian.contracts.services import InvestigationSink, UpstreamError

Behaviour = Literal["report", "raise", "upstream", "incomplete", "fail", "block"]

REPORT = Report(
    summary="Synthetic test summary.",
    findings=[Finding(claim="Synthetic claim.", evidence_ids=["E1"], strength="moderate")],
    actions=[
        Action(action="Check sensor S060.", rationale="Synthetic.", evidence_ids=["E1"]),
        Action(action="Recalibrate chamber.", rationale="Synthetic.", evidence_ids=["E1"]),
        Action(action="Hold lot.", rationale="Synthetic.", evidence_ids=["E1"]),
    ],
    numbers=[
        NumberRef(value=0.5, as_written="0.5", unit="probability", evidence_id="E1", path="/risk")
    ],
    limitations=["Synthetic test report."],
)

VERIFICATION = Verification(
    passed=True,
    rounds=0,
    numbers_checked=1,
    numbers_matched=1,
    issues=[],
    claims=[],
    verifier_model="test-verifier",
)


def _step(status: Literal["running", "completed"], llm: list[CallUsage]) -> InvestigationStep:
    return InvestigationStep(
        index=0,
        node="evidence",
        status=status,
        title="Read the risk of unit 1043",
        started_at=datetime(2026, 10, 14, 8, 0, tzinfo=UTC),
        finished_at=None if status == "running" else datetime(2026, 10, 14, 8, 0, 1, tzinfo=UTC),
        tool="get_risk",
        evidence_ids=[] if status == "running" else ["E1"],
        llm=llm,
    )


CALLS = [
    CallUsage(
        role="investigator",
        model_id="test-model",
        tokens_in=100,
        tokens_out=20,
        tokens_reasoning=5,
        points=0.001,
        latency_ms=900,
        cached=False,
    ),
    CallUsage(
        role="writer",
        model_id="test-writer",
        tokens_in=50,
        tokens_out=10,
        tokens_reasoning=0,
        points=0.0,
        latency_ms=3,
        cached=True,
    ),
]


class FakeRunner:
    """Follows `behaviour`; records every run and resume."""

    def __init__(self, behaviour: Behaviour = "report") -> None:
        self.behaviour: Behaviour = behaviour
        self.runs: list[str] = []
        self.as_of: list[int | None] = []
        self.resumes: list[tuple[str, Decision]] = []
        self.release = asyncio.Event()
        self.started = asyncio.Event()

    async def run(
        self,
        investigation_id: str,
        trigger: InvestigationTrigger,
        sink: InvestigationSink,
        *,
        as_of: int | None = None,
    ) -> None:
        self.runs.append(investigation_id)
        self.as_of.append(as_of)
        self.started.set()
        await sink.status("running")
        if self.behaviour == "block":
            await self.release.wait()
        if self.behaviour == "raise":
            raise RuntimeError("synthetic crash")
        if self.behaviour == "upstream":
            raise UpstreamError("The model service answered 502.")
        await sink.step(_step("running", []))
        await sink.evidence(
            Evidence(
                evidence_id="E1",
                investigation_id=investigation_id,
                tool="get_risk",
                arguments={"unit_id": 1043},
                data={"risk": 0.5},
                summary="Risk of unit 1043.",
                created_at=datetime(2026, 10, 14, 8, 0, tzinfo=UTC),
                source=None,
            )
        )
        await sink.step(_step("completed", CALLS))
        if self.behaviour == "fail":
            await sink.error(
                Problem(title="Model error", status=502, code="upstream_error", detail="test")
            )
            await sink.status("failed")
            return
        if self.behaviour == "incomplete":
            return
        await sink.report(REPORT, round=0)
        await sink.verification(VERIFICATION, round=0)
        await sink.status("awaiting_decision")

    async def resume(
        self, investigation_id: str, decision: Decision, sink: InvestigationSink
    ) -> None:
        self.resumes.append((investigation_id, decision))
        await sink.status("running")  # ignored: the API sets the final status
