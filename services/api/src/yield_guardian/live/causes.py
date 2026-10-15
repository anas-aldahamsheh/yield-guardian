"""Literature causes for the patterns a run predicted: the curated table, filtered (PLAN_V2 §7.1).

The table is ``docs/knowledge/pattern_causes.json``, the same one the API serves at
/api/v1/knowledge/patterns: per WM-811K defect pattern, causes proposed in open-access papers,
each with exact quotes and their location. They are hypotheses for an engineer to check, never a
diagnosis; the table's own `framing` sentence travels with every answer.
"""

from collections.abc import Sequence
from pathlib import Path

from yield_guardian.contracts.knowledge import Confidence, PatternCause, PatternCauses
from yield_guardian.contracts.wafer import WaferLabel
from yield_guardian.knowledge.service import (
    PATTERN_CAUSES_FILE,
    LiteratureKnowledge,
    load_pattern_causes,
)

EVIDENCE_RANK: dict[Confidence, int] = {"high": 0, "medium": 1, "low": 2}


class LiteratureCauses:
    """Implements :class:`~yield_guardian.live.protocols.PatternCausesSource`."""

    def __init__(self, table: PatternCauses) -> None:
        self.table = table

    @classmethod
    def from_directory(cls, directory: Path) -> "LiteratureCauses":
        """Read and check ``pattern_causes.json`` in a knowledge directory (KnowledgeError)."""
        return cls(load_pattern_causes(directory / PATTERN_CAUSES_FILE))

    @classmethod
    def from_knowledge(cls, knowledge: LiteratureKnowledge) -> "LiteratureCauses":
        """The table the knowledge service already loaded and serves."""
        return cls(knowledge.causes)

    def causes(self, labels: Sequence[WaferLabel]) -> PatternCauses:
        """The causes of the given patterns with the sources they quote.

        Patterns keep the order asked (first mention); within a pattern, causes are ranked by
        the support the literature gives them (medium before low), then in table order. A
        pattern the table has no entry for (such as "none") adds nothing. Sources are those the
        returned causes quote, in table order.
        """
        wanted: dict[WaferLabel, int] = {}
        for label in labels:
            wanted.setdefault(label, len(wanted))
        ranked = sorted(
            (
                (wanted[cause.label], EVIDENCE_RANK[cause.confidence], position, cause)
                for position, cause in enumerate(self.table.causes)
                if cause.label in wanted
            ),
            key=lambda entry: entry[:3],
        )
        causes: list[PatternCause] = [entry[3] for entry in ranked]
        cited = {quote.source_id for cause in causes for quote in cause.quotes}
        return PatternCauses(
            framing=self.table.framing,
            causes=causes,
            sources=[s for s in self.table.sources if s.source_id in cited],
        )
