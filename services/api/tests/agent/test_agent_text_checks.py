"""Causal wording, JSON Pointers, and free-text grounding against evidence (synthetic values)."""

from __future__ import annotations

import pytest

from tests.agent.helpers import evidence
from yield_guardian.agent.grounding import (
    REDACTED,
    REDACTED_IDENTIFIER,
    EvidenceFacts,
    check_text,
    redact_unverified,
)
from yield_guardian.agent.pointer import PointerError, resolve
from yield_guardian.agent.wording import causal_phrases

# -- wording --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "labels"),
    [
        ("S060 caused the failure.", ["cause"]),
        ("This causes drift.", ["cause"]),
        ("The root cause is S060.", ["root cause"]),
        ("Root-causes include drift.", ["root cause"]),
        ("Failures are due to drift.", ["due to"]),
        ("Because of the drift, risk rose.", ["because of"]),
        ("Owing to S060, risk rose.", ["owing to"]),
        ("Drift resulted in failures.", ["result in"]),
        ("Drift led to failures and leads to more.", ["lead to", "lead to"]),
        ("S060 is responsible for the alarm.", ["responsible for"]),
        ("The alarm is attributable to S060.", ["attributable to"]),
        ("Risk is driven by S060; S060 drives it.", ["drive", "drive"]),
        ("Heat induced the pattern.", ["induce"]),
    ],
)
def test_causal_phrases_are_found(text: str, labels: list[str]) -> None:
    assert [p.label for p in causal_phrases(text)] == labels


@pytest.mark.parametrize(
    "text",
    [
        "S060 is associated with failure.",
        "The evidence shows association, not causation.",
        "Causal claims need an experiment.",
        "The risk coincides with the T2 alarm.",
        "Drive-in diffusion step",  # 'drive' alone, not drives/driven/driving/drove
    ],
)
def test_association_wording_passes(text: str) -> None:
    assert causal_phrases(text) == []


def test_root_cause_is_reported_once() -> None:
    (phrase,) = causal_phrases("The root cause is unknown.")
    assert phrase.text == "root cause"


# -- JSON Pointer ---------------------------------------------------------------------------

DOC = {"a": [{"b": 1}, {"c/d": 2, "e~f": 3}], "": 4, "s": "text"}


@pytest.mark.parametrize(
    ("pointer", "value"),
    [("", DOC), ("/a/0/b", 1), ("/a/1/c~1d", 2), ("/a/1/e~0f", 3), ("/", 4), ("/s", "text")],
)
def test_resolve(pointer: str, value: object) -> None:
    assert resolve(DOC, pointer) == value


@pytest.mark.parametrize(
    "pointer", ["a", "/missing", "/a/2", "/a/-1", "/a/01", "/a/x", "/s/0", "/a/1/e~2f"]
)
def test_resolve_refuses_bad_pointers(pointer: str) -> None:
    with pytest.raises(PointerError):
        resolve(DOC, pointer)


# -- grounding ------------------------------------------------------------------------------


@pytest.fixture
def facts() -> EvidenceFacts:
    items = [
        evidence(
            "E1",
            {"unit_id": 1062, "risk": 0.184, "shap": -0.42, "sensor": "S060", "lot": "lot47542"},
            unit_id=1062,
        ),
        evidence("E2", {"windows": [{"window_id": 3}], "timestamp": "2008-09-24T15:05:00Z"}),
    ]
    return EvidenceFacts.build(items)


def test_facts_index_numbers_strings_and_identifiers(facts: EvidenceFacts) -> None:
    assert 0.184 in facts.numbers
    assert "S060" in facts.strings
    assert facts.ints["unit"] == {1062}
    assert facts.ints["window"] == {3}
    assert facts.evidence_ids == {"E1", "E2"}
    assert "lot47542" in facts.known_identifiers


def test_supported_text_passes(facts: EvidenceFacts) -> None:
    check = check_text(
        "Unit 1062 has risk 18.4% (E1); S060 shows -0.42 in lot47542 on 2008-09-24.", facts
    )
    assert check.unverified == ()
    assert check.unsupported_identifiers == ()


def test_unsupported_numbers_and_identifiers_are_reported(facts: EvidenceFacts) -> None:
    check = check_text("Unit 1043 has risk 0.25 at S099 (E7).", facts)
    assert [n.text for n in check.unverified] == ["0.25"]
    assert sorted(v for _, v in check.unsupported_identifiers) == ["1043", "E7", "S099"]


def test_redaction_replaces_only_what_failed(facts: EvidenceFacts) -> None:
    text, check = redact_unverified("Risk 0.184, not 0.25; sensor S099; unit 1062.", facts)
    assert text == (f"Risk 0.184, not {REDACTED}; sensor {REDACTED_IDENTIFIER}; unit 1062.")
    assert len(check.numbers) == 2


def test_trigger_names_count_as_known(facts: EvidenceFacts) -> None:
    extra = EvidenceFacts.build([], strings=["AL-1043-t2"], units=[1043])
    check = check_text("Alarm AL-1043-t2 on unit 1043.", extra)
    assert check.unsupported_identifiers == ()
