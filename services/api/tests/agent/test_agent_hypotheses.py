"""Report hypotheses (PLAN_V2 7.3): sources, evidence, numbers, wording, assessments; and the
default that keeps every report written before hypotheses valid. Values are synthetic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.agent.helpers import evidence
from yield_guardian.agent.grounding import EvidenceFacts, check_text
from yield_guardian.agent.verifier import (
    REPORT_REDACTION,
    check_numbers_and_citations,
    shown_report,
    text_fields,
)
from yield_guardian.agent.writer import REPORT_SCHEMA_TEXT
from yield_guardian.contracts.investigation import (
    InvestigationEvent,
    InvestigationTrigger,
    Report,
    ReportEvent,
    VerificationIssue,
)
from yield_guardian.services.recorded import read_runs

RECORDED = Path(__file__).resolve().parents[4] / "docs" / "recorded" / "investigations.json"
SOURCES = frozenset({"zheng2021", "xu2022"})
E1 = evidence(
    "E1",
    {"pattern": {"top_label": "Edge-Ring", "top_probability": 0.93}, "radial": [0.0, 0.81]},
    tool="get_run_wafer",
    run_id="run_testcase0001",
    wafer_index=0,
)
E2 = evidence(
    "E2", {"similar_recorded_labels": {"Edge-Ring": 7, "Center": 1}}, tool="get_run_wafer"
)
EVIDENCE = {"E1": E1, "E2": E2}


def hypothesis(
    text: str = "The Edge-Ring pattern is associated in the literature with uneven heating.",
    *,
    sources: list[str] | None = None,
    for_: list[tuple[str, str]] | None = None,
    against: list[tuple[str, str]] | None = None,
    assessment: str = "supported",
) -> dict[str, Any]:
    def items(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
        return [{"evidence_id": e, "observation": o} for e, o in pairs]

    return {
        "hypothesis": text,
        "source_ids": ["zheng2021"] if sources is None else sources,
        "evidence_for": items(
            [("E1", "The pattern is Edge-Ring with probability 0.93.")] if for_ is None else for_
        ),
        "evidence_against": items(against or []),
        "assessment": assessment,
    }


PROBABILITY = {
    "value": 0.93,
    "as_written": "0.93",
    "unit": "probability",
    "evidence_id": "E1",
    "path": "/pattern/top_probability",
}


def report(*hypotheses: dict[str, Any], numbers: list[dict[str, Any]] | None = None) -> Report:
    return Report.model_validate(
        {
            "summary": "The wafer shows an Edge-Ring pattern.",
            "findings": [],
            "actions": [],
            "numbers": [PROBABILITY] if numbers is None else numbers,
            "limitations": ["Association only."],
            "hypotheses": list(hypotheses),
        }
    )


def issues(r: Report, sources: frozenset[str] | None = SOURCES) -> list[tuple[str, str]]:
    found: list[VerificationIssue] = check_numbers_and_citations(
        r, EVIDENCE, known_sources=sources
    ).issues
    return [(i.code, i.location) for i in found]


def test_a_grounded_hypothesis_passes() -> None:
    assert issues(report(hypothesis())) == []


def test_an_unknown_source_is_rejected() -> None:
    found = issues(report(hypothesis(sources=["zheng2021", "made_up_2020"])))
    assert found == [("unknown_source", "hypotheses[0].source_ids")]


def test_sources_cannot_be_confirmed_without_the_knowledge_base() -> None:
    assert issues(report(hypothesis()), sources=None) == [
        ("unknown_source", "hypotheses[0].source_ids")
    ]
    assert issues(report(hypothesis(sources=[])), sources=None) == []  # a sensor-track hypothesis


def test_evidence_not_returned_in_this_investigation_is_rejected() -> None:
    found = issues(report(hypothesis(against=[("E7", "A similar wafer is Center.")])))
    assert found == [("unknown_evidence", "hypotheses[0].evidence_against[0].evidence_id")]


def test_an_unlisted_number_in_an_observation_is_rejected_and_hidden() -> None:
    r = report(hypothesis(for_=[("E2", "7 of the similar wafers are recorded as Edge-Ring.")]))
    found = issues(r)
    assert found == [("number_not_listed", "hypotheses[0].evidence_for[0].observation")]
    check = check_numbers_and_citations(r, EVIDENCE, known_sources=SOURCES)
    shown = shown_report(r, check.redactions)
    assert shown.hypotheses[0].evidence_for[0].observation == (
        f"{REPORT_REDACTION} of the similar wafers are recorded as Edge-Ring."
    )


def test_a_number_from_evidence_the_observation_does_not_cite_is_flagged() -> None:
    r = report(hypothesis(for_=[("E2", "The pattern is Edge-Ring with probability 0.93.")]))
    assert issues(r) == [("missing_citation", "hypotheses[0].evidence_for[0].observation")]


def test_a_number_that_does_not_match_its_evidence_is_rejected() -> None:
    wrong = {**PROBABILITY, "value": 0.97, "as_written": "0.97"}
    r = report(
        hypothesis(for_=[("E1", "The pattern is Edge-Ring with probability 0.97.")]),
        numbers=[wrong],
    )
    assert issues(r) == [("number_mismatch", "hypotheses[0].evidence_for[0].observation")]


def test_causal_wording_in_a_hypothesis_is_rejected() -> None:
    r = report(hypothesis("The Edge-Ring pattern is caused by uneven heating."))
    assert issues(r) == [("causal_wording", "hypotheses[0].hypothesis")]


def test_an_assessment_needs_the_evidence_it_claims() -> None:
    no_support = hypothesis(for_=[], assessment="supported")
    no_counter = hypothesis(assessment="not_supported")
    undecided = hypothesis(for_=[], assessment="inconclusive")
    found = issues(report(no_support, no_counter, undecided))
    assert found == [
        ("assessment_without_evidence", "hypotheses[0].assessment"),
        ("assessment_without_evidence", "hypotheses[1].assessment"),
    ]


def test_identifiers_of_a_run_must_exist_in_the_evidence() -> None:
    trigger = InvestigationTrigger(kind="run_alarm", ref="run_testcase0001:RA-2")
    r = Report.model_validate(
        {
            **report(hypothesis()).model_dump(mode="json"),
            "summary": "Alarm RA-2 of run_testcase0001 and alarm RA-9 of run_otherrun99.",
        }
    )
    found = check_numbers_and_citations(r, EVIDENCE, trigger=trigger, known_sources=SOURCES)
    assert sorted(i.message for i in found.issues) == [
        "mentions alarm RA-9, which no evidence contains",
        "mentions run run_otherrun99, which no evidence contains",
    ]


def test_every_hypothesis_text_is_a_checked_field() -> None:
    r = report(hypothesis(against=[("E2", "One similar wafer is Center.")]))
    locations = [f.location for f in text_fields(r)]
    assert locations[-3:] == [
        "hypotheses[0].hypothesis",
        "hypotheses[0].evidence_for[0].observation",
        "hypotheses[0].evidence_against[0].observation",
    ]
    cites = {f.location: f.cites for f in text_fields(r)}
    assert cites["hypotheses[0].hypothesis"] == ("E1", "E2")


def test_reports_without_hypotheses_stay_valid() -> None:
    old = {"summary": "s", "findings": [], "actions": [], "numbers": [], "limitations": []}
    assert Report.model_validate(old).hypotheses == []
    assert '"hypotheses"' in REPORT_SCHEMA_TEXT  # the writer is shown the field


def test_the_recorded_investigations_stay_valid() -> None:
    recorded = read_runs(RECORDED)
    assert recorded.runs
    for run in recorded.runs:
        assert run.investigation.report is not None
        assert run.investigation.report.hypotheses == []
        events = [InvestigationEvent.model_validate(e).root for e in run.events]
        reports = [e for e in events if isinstance(e, ReportEvent)]
        assert reports
        assert all(e.report.hypotheses == [] for e in reports)
        assert run.paused_state is not None
        assert Report.model_validate(run.paused_state["report"]).hypotheses == []


def test_a_digit_only_name_does_not_exempt_numbers() -> None:
    """A lot named "7" in a user's file must not turn every 7 into a name."""
    lot = evidence("E1", {"lot": "7", "wafers": 3}, tool="get_run_lot")
    facts = EvidenceFacts.build([lot])
    assert "7" not in facts.known_identifiers
    assert [n.text for n in check_text("7 wafers failed", facts).unverified] == ["7"]
    named = EvidenceFacts.build([evidence("E1", {"lot": "L7A", "unit_id": "12"})])
    assert "L7A" in named.known_identifiers
    assert 12 in named.ints["unit"]  # a run unit labelled 12 may be written "unit 12"
