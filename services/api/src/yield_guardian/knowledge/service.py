"""The knowledge service: literature search and the pattern-to-cause table.

The table (``docs/knowledge/pattern_causes.json``) lists, for each WM-811K defect pattern, causes
proposed in open-access literature, each with exact quotes and their location in the source.
It is framed as hypotheses for an engineer to check, never as a diagnosis. The search index
holds those quotes plus any reviewed Markdown documents in ``docs/knowledge/corpus/``: in memory
at first, then in PostgreSQL when the database is available (``agent.wiring``).
"""

from __future__ import annotations

from pathlib import Path

from yield_guardian.contracts.knowledge import (
    KnowledgeSearchResult,
    KnowledgeSource,
    PatternCauses,
)
from yield_guardian.contracts.services import InvalidArgumentError
from yield_guardian.contracts.wafer import WaferLabel
from yield_guardian.knowledge.chunking import Chunk, chunk_markdown
from yield_guardian.knowledge.ingest import load_markdown, quote_chunks
from yield_guardian.knowledge.search import InMemoryFullTextIndex, SearchIndex

PATTERN_CAUSES_FILE = "pattern_causes.json"
CORPUS_DIR = "corpus"
MAX_RESULTS = 20

Document = tuple[KnowledgeSource, tuple[Chunk, ...]]


class KnowledgeError(ValueError):
    """The knowledge files are missing or inconsistent."""


def check_pattern_causes(causes: PatternCauses) -> None:
    """Every quote cites a listed source; source IDs are unique; every source is cited."""
    ids = [s.source_id for s in causes.sources]
    if len(ids) != len(set(ids)):
        raise KnowledgeError("source IDs repeat")
    cited = {q.source_id for c in causes.causes for q in c.quotes}
    unknown = cited - set(ids)
    if unknown:
        raise KnowledgeError(f"quotes cite unknown sources: {', '.join(sorted(unknown))}")
    unused = set(ids) - cited
    if unused:
        raise KnowledgeError(f"sources never quoted: {', '.join(sorted(unused))}")
    for source in causes.sources:
        if not source.open_access:
            raise KnowledgeError(f"{source.source_id} is not open access")
        if not (source.doi or source.url):
            raise KnowledgeError(f"{source.source_id} has neither a DOI nor a URL")


def load_pattern_causes(path: Path) -> PatternCauses:
    try:
        causes = PatternCauses.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise KnowledgeError(f"{path} cannot be read: {error}") from error
    check_pattern_causes(causes)
    return causes


def load_documents(directory: Path) -> tuple[PatternCauses, list[Document]]:
    """The pattern-cause table and every searchable document: the table's quotes, then the
    reviewed corpus files."""
    causes = load_pattern_causes(directory / PATTERN_CAUSES_FILE)
    sources = {s.source_id: s for s in causes.sources}
    documents: list[Document] = [
        (sources[source_id], tuple(chunks)) for source_id, chunks in quote_chunks(causes).items()
    ]
    corpus = directory / CORPUS_DIR
    if corpus.is_dir():
        for path in sorted(corpus.glob("*.md")):
            source, pages = load_markdown(path)
            known = sources.get(source.source_id)
            if known is not None and known != source:
                raise KnowledgeError(f"{path.name} disagrees with the source list")
            documents.append((source, tuple(chunk_markdown(source.source_id, pages))))
    return causes, documents


class LiteratureKnowledge:
    """Implements :class:`~yield_guardian.contracts.services.KnowledgeService`."""

    def __init__(
        self, causes: PatternCauses, index: SearchIndex, documents: list[Document] | None = None
    ) -> None:
        self.causes = causes
        self.index = index
        self.documents: list[Document] = documents or []
        """What the index holds, so another index can be filled with the same chunks."""

    @classmethod
    def from_directory(cls, directory: Path) -> LiteratureKnowledge:
        causes, documents = load_documents(directory)
        index = InMemoryFullTextIndex()
        for source, chunks in documents:
            index.add(source, chunks)
        return cls(causes, index, documents)

    async def search(self, query: str, *, limit: int = 5) -> KnowledgeSearchResult:
        text = " ".join(query.split())
        if not 2 <= len(text) <= 200:
            raise InvalidArgumentError("the query must have 2 to 200 characters")
        if not 1 <= limit <= MAX_RESULTS:
            raise InvalidArgumentError(f"limit must be between 1 and {MAX_RESULTS}")
        hits = await self.index.search_hits(text, limit=limit)
        return KnowledgeSearchResult(query=text, hits=hits, method=self.index.method)

    async def pattern_causes(self, label: WaferLabel | None = None) -> PatternCauses:
        if label is None:
            return self.causes
        causes = [c for c in self.causes.causes if c.label == label]
        cited = {q.source_id for c in causes for q in c.quotes}
        sources: list[KnowledgeSource] = [s for s in self.causes.sources if s.source_id in cited]
        return PatternCauses(framing=self.causes.framing, causes=causes, sources=sources)
