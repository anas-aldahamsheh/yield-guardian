"""The literature causes of a run's patterns: the curated table (docs/knowledge), filtered."""

from typing import get_args

import pytest

from tests.live.wafers.conftest import KNOWLEDGE
from yield_guardian.contracts.wafer import WaferLabel
from yield_guardian.knowledge.service import LiteratureKnowledge
from yield_guardian.live.causes import LiteratureCauses

LABELS: tuple[WaferLabel, ...] = get_args(WaferLabel)


@pytest.mark.parametrize("label", LABELS)
async def test_one_pattern_gives_what_the_knowledge_api_serves(
    causes: LiteratureCauses, label: WaferLabel
) -> None:
    served = await LiteratureKnowledge.from_directory(KNOWLEDGE).pattern_causes(label)
    live = causes.causes([label])
    assert live.framing == served.framing
    assert sorted(live.causes, key=lambda c: c.hypothesis) == sorted(
        served.causes, key=lambda c: c.hypothesis
    )
    assert live.sources == served.sources


def test_several_patterns_keep_the_order_asked_and_rank_by_evidence(
    causes: LiteratureCauses,
) -> None:
    result = causes.causes(["Scratch", "Center", "none", "Scratch", "Edge-Ring"])
    labels = [c.label for c in result.causes]
    assert labels == sorted(labels, key=["Scratch", "Center", "Edge-Ring"].index)
    assert {"Scratch", "Center", "Edge-Ring"} == set(labels)
    rank = {"high": 0, "medium": 1, "low": 2}
    for label in set(labels):
        levels = [rank[c.confidence] for c in result.causes if c.label == label]
        assert levels == sorted(levels)
    cited = {q.source_id for c in result.causes for q in c.quotes}
    assert {s.source_id for s in result.sources} == cited
    assert "hypotheses" in result.framing


def test_no_pattern_gives_no_cause(causes: LiteratureCauses) -> None:
    cases: list[list[WaferLabel]] = [[], ["none"]]
    for labels in cases:
        result = causes.causes(labels)
        assert result.causes == []
        assert result.sources == []
        assert result.framing == causes.table.framing


def test_built_from_the_loaded_knowledge_service() -> None:
    knowledge = LiteratureKnowledge.from_directory(KNOWLEDGE)
    assert LiteratureCauses.from_knowledge(knowledge).table is knowledge.causes
