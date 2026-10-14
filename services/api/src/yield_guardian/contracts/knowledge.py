"""Pattern-to-cause knowledge from open-access literature, shown as hypotheses to check."""

from typing import Literal

from pydantic import Field

from yield_guardian.contracts.base import Contract
from yield_guardian.contracts.wafer import WaferLabel

Confidence = Literal["high", "medium", "low"]


class KnowledgeSource(Contract):
    source_id: str
    title: str
    authors: list[str]
    venue: str | None
    year: int | None
    doi: str | None
    url: str | None
    open_access: bool


class SourceQuote(Contract):
    source_id: str
    quote: str = Field(description="Exact statement as read in the source.")
    location: str = Field(examples=["p. 4, section III.B"])


class PatternCause(Contract):
    label: WaferLabel
    hypothesis: str
    confidence: Confidence
    quotes: list[SourceQuote] = Field(min_length=1)


class PatternCauses(Contract):
    framing: str = Field(description="How to read the table: hypotheses to check, not conclusions.")
    causes: list[PatternCause]
    sources: list[KnowledgeSource]


class KnowledgeHit(Contract):
    chunk_id: str
    source: KnowledgeSource
    location: str | None
    snippet: str
    rank: float


class KnowledgeSearchResult(Contract):
    query: str
    hits: list[KnowledgeHit]
    method: str
