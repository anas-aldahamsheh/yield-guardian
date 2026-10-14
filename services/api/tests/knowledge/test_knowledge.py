"""Knowledge base: the curated pattern-cause table, chunking with provenance, search, ingestion.

Documents built inside these tests are synthetic text written for the tests; the pattern-cause
table is the real curated file in docs/knowledge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest
import respx

from tests.llm.helpers import HOST, make_client
from yield_guardian.agent.wiring import DEFAULT_KNOWLEDGE_DIR, install_knowledge, knowledge_dir
from yield_guardian.agent.wording import causal_phrases
from yield_guardian.contracts.knowledge import KnowledgeSource, PatternCauses
from yield_guardian.contracts.services import InvalidArgumentError
from yield_guardian.contracts.wafer import WaferLabel
from yield_guardian.core.settings import Settings
from yield_guardian.knowledge.chunking import chunk_markdown
from yield_guardian.knowledge.ingest import (
    ingest_document,
    ingest_markdown,
    load_markdown,
    quote_chunks,
    save_markdown,
)
from yield_guardian.knowledge.search import InMemoryFullTextIndex, snippet, stem, terms
from yield_guardian.knowledge.service import (
    KnowledgeError,
    LiteratureKnowledge,
    check_pattern_causes,
    load_pattern_causes,
)
from yield_guardian.services.registry import ServiceRegistry

TABLE = DEFAULT_KNOWLEDGE_DIR / "pattern_causes.json"
MD = DEFAULT_KNOWLEDGE_DIR / "pattern_causes.md"
SYNTHETIC = KnowledgeSource(
    source_id="synthetic1",
    title="Synthetic test document",
    authors=["Test Author"],
    venue=None,
    year=None,
    doi=None,
    url="https://example.org/synthetic.pdf",
    open_access=True,
)


# -- the curated table ----------------------------------------------------------------------


def test_the_curated_table_is_consistent() -> None:
    causes = load_pattern_causes(TABLE)
    assert causes.causes
    labels = set(get_args(WaferLabel))
    assert {c.label for c in causes.causes} <= labels
    for source in causes.sources:
        assert source.open_access
        assert source.doi or source.url


def test_the_table_is_framed_as_hypotheses_and_has_no_high_confidence() -> None:
    causes = load_pattern_causes(TABLE)
    assert "hypotheses" in causes.framing
    assert {c.confidence for c in causes.causes} <= {"medium", "low"}
    for cause in causes.causes:
        assert causal_phrases(cause.hypothesis) == [], cause.hypothesis
        if cause.confidence == "medium":
            assert len({q.source_id for q in cause.quotes}) >= 2


def test_every_quote_is_short_and_shown_in_the_markdown() -> None:
    causes = load_pattern_causes(TABLE)
    markdown = MD.read_text(encoding="utf-8")
    for cause in causes.causes:
        assert cause.hypothesis in markdown
        for quote in cause.quotes:
            assert len(quote.quote) <= 125
            assert f'"{quote.quote}"' in markdown
    for source in causes.sources:
        assert source.title in markdown


def test_patterns_without_a_source_are_said_to_have_none() -> None:
    causes = load_pattern_causes(TABLE)
    covered = {c.label for c in causes.causes}
    for label in set(get_args(WaferLabel)) - covered - {"none"}:
        assert label in causes.framing


def test_inconsistent_tables_are_refused() -> None:
    causes = load_pattern_causes(TABLE)
    data = causes.model_dump()
    data["causes"][0]["quotes"][0]["source_id"] = "nowhere"
    with pytest.raises(KnowledgeError, match="unknown sources"):
        check_pattern_causes(PatternCauses.model_validate(data))
    extra = causes.model_dump()
    extra["sources"].append(SYNTHETIC.model_dump())
    with pytest.raises(KnowledgeError, match="never quoted"):
        check_pattern_causes(PatternCauses.model_validate(extra))
    closed = causes.model_dump()
    closed["sources"][0]["open_access"] = False
    with pytest.raises(KnowledgeError, match="not open access"):
        check_pattern_causes(PatternCauses.model_validate(closed))


def test_a_missing_table_is_a_knowledge_error(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeError, match="cannot be read"):
        load_pattern_causes(tmp_path / "pattern_causes.json")


# -- chunking -------------------------------------------------------------------------------


def test_chunks_keep_page_and_section() -> None:
    pages = [
        (0, "# 1 Introduction\n\nFirst paragraph.\n\nSecond paragraph."),
        (1, "Still introduction on page two.\n\n## 2.1 Edge defects\n\nEdge text."),
    ]
    chunks = chunk_markdown("synthetic1", pages)
    assert [(c.location, c.text) for c in chunks] == [
        ("p. 1, section 1 Introduction", "First paragraph.\n\nSecond paragraph."),
        ("p. 2, section 1 Introduction", "Still introduction on page two."),
        ("p. 2, section 2.1 Edge defects", "Edge text."),
    ]
    assert len({c.chunk_id for c in chunks}) == 3
    assert all(c.chunk_id.startswith("synthetic1-") for c in chunks)


def test_long_paragraphs_are_cut_at_sentences_within_the_limit() -> None:
    paragraph = " ".join(f"Sentence number {i} says something useful." for i in range(60))
    chunks = chunk_markdown("synthetic1", [(0, paragraph)], max_chars=200)
    assert all(len(c.text) <= 200 for c in chunks)
    assert " ".join(c.text for c in chunks) == paragraph
    unbroken = "x" * 450
    assert [len(c.text) for c in chunk_markdown("s", [(0, unbroken)], max_chars=200)] == [
        200,
        200,
        50,
    ]


def test_chunking_refuses_tiny_limits() -> None:
    with pytest.raises(ValueError, match="at least 100"):
        chunk_markdown("s", [(0, "x")], max_chars=10)


# -- search ---------------------------------------------------------------------------------


def test_terms_and_stems() -> None:
    assert stem("rings") == "ring"
    assert stem("scratches") == "scratch"
    assert stem("caused") == "caus"
    assert terms("What causes Edge-Ring patterns?") == ["caus", "edge-ring", "edg", "ring", "pattern"]  # fmt: skip


def test_bm25_ranks_the_most_specific_chunk_first() -> None:
    index = InMemoryFullTextIndex()
    pages = [
        (0, "Scratches come from handling robots."),
        (1, "Edge rings appear near the wafer edge after etching. Edge rings are common."),
        (2, "The edge of the table is wooden."),
    ]
    index.add(SYNTHETIC, chunk_markdown(SYNTHETIC.source_id, pages))
    hits = index.search("edge ring etching")
    assert [h.location for h in hits] == ["p. 2", "p. 3"]
    assert hits[0].rank > hits[1].rank > 0
    assert hits[0].source == SYNTHETIC
    assert index.search("photolithography") == []
    assert index.search("the of and") == []


def test_adding_a_chunk_twice_or_to_the_wrong_source_is_handled() -> None:
    index = InMemoryFullTextIndex()
    chunks = chunk_markdown(SYNTHETIC.source_id, [(0, "Some text about rings.")])
    assert index.add(SYNTHETIC, chunks) == 1
    assert index.add(SYNTHETIC, chunks) == 0
    other = SYNTHETIC.model_copy(update={"source_id": "other"})
    with pytest.raises(ValueError, match="belongs to"):
        index.add(other, chunks)


def test_snippets_are_exact_text_around_the_matches() -> None:
    text = " ".join(["filler"] * 100) + " the edge ring appears here " + " ".join(["more"] * 100)
    shown = snippet(text, terms("edge ring"))
    assert "edge ring appears" in shown
    assert shown.strip("…") in text
    assert len(shown) <= 322


# -- the service ----------------------------------------------------------------------------


async def test_search_returns_exact_quotes_with_their_source_and_location() -> None:
    knowledge = LiteratureKnowledge.from_directory(DEFAULT_KNOWLEDGE_DIR)
    result = await knowledge.search("Scratch handling")
    assert result.hits
    causes = load_pattern_causes(TABLE)
    quotes = {(q.source_id, q.quote, q.location) for c in causes.causes for q in c.quotes}
    for hit in result.hits:
        assert (hit.source.source_id, hit.snippet, hit.location) in quotes
    assert "BM25" in result.method


async def test_search_arguments_are_checked() -> None:
    knowledge = LiteratureKnowledge.from_directory(DEFAULT_KNOWLEDGE_DIR)
    with pytest.raises(InvalidArgumentError):
        await knowledge.search("x")
    with pytest.raises(InvalidArgumentError):
        await knowledge.search("edge ring", limit=0)


async def test_pattern_causes_filter_by_label_with_their_sources() -> None:
    knowledge = LiteratureKnowledge.from_directory(DEFAULT_KNOWLEDGE_DIR)
    everything = await knowledge.pattern_causes()
    scratch = await knowledge.pattern_causes("Scratch")
    assert scratch.causes
    assert all(c.label == "Scratch" for c in scratch.causes)
    cited = {q.source_id for c in scratch.causes for q in c.quotes}
    assert {s.source_id for s in scratch.sources} == cited
    assert len(everything.causes) > len(scratch.causes)
    assert (await knowledge.pattern_causes("none")).causes == []


async def test_a_reviewed_corpus_document_is_searchable(tmp_path: Path) -> None:
    directory = tmp_path / "knowledge"
    (directory / "corpus").mkdir(parents=True)
    (directory / "pattern_causes.json").write_text(TABLE.read_text(encoding="utf-8"))
    index = InMemoryFullTextIndex()
    document = ingest_markdown(index, SYNTHETIC, [(0, "# Methods\n\nA synthetic sentence about zebra stripes.")])  # fmt: skip
    save_markdown(directory / "corpus", document)
    knowledge = LiteratureKnowledge.from_directory(directory)
    (hit,) = (await knowledge.search("zebra stripes")).hits
    assert (hit.source.source_id, hit.location) == ("synthetic1", "p. 1, section Methods")


def test_markdown_files_round_trip(tmp_path: Path) -> None:
    document = ingest_markdown(InMemoryFullTextIndex(), SYNTHETIC, [(0, "Page one."), (3, "Page four.")])  # fmt: skip
    path = save_markdown(tmp_path, document)
    assert load_markdown(path) == (SYNTHETIC, ((0, "Page one."), (3, "Page four.")))
    path.write_text("no header\n")
    with pytest.raises(ValueError, match="source header"):
        load_markdown(path)


def test_quote_chunks_deduplicate_shared_quotes() -> None:
    chunks = quote_chunks(load_pattern_causes(TABLE))
    for items in chunks.values():
        texts = [c.text for c in items]
        assert len(texts) == len(set(texts))


async def test_ocr_ingestion_against_a_mocked_endpoint(respx_mock: respx.Router) -> None:
    route = respx_mock.post(host=HOST, path__regex=r"/ocr$").respond(
        200,
        json={
            "pages": [
                {"index": 1, "markdown": "Second page text."},
                {"index": 0, "markdown": "# Intro\n\nFirst page."},
            ],
            "usage_info": {"pages_processed": 2},
        },
    )
    index = InMemoryFullTextIndex()
    document = await ingest_document(index, make_client(), SYNTHETIC, "https://example.org/synthetic.pdf", pages="0-1")  # fmt: skip
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "model": "MinerU2.5-Pro",
        "document": {"type": "document_url", "document_url": "https://example.org/synthetic.pdf"},
        "pages": "0-1",
    }
    assert [p for p, _ in document.pages] == [0, 1]
    assert [c.location for c in document.chunks] == ["p. 1, section Intro", "p. 2, section Intro"]
    assert len(index) == 2


async def test_ingestion_refuses_closed_sources_and_plain_http() -> None:
    closed = SYNTHETIC.model_copy(update={"open_access": False})
    with pytest.raises(ValueError, match="not open access"):
        await ingest_document(InMemoryFullTextIndex(), make_client(), closed, "https://example.org/x.pdf")  # fmt: skip
    with pytest.raises(ValueError, match="https only"):
        await ingest_document(InMemoryFullTextIndex(), make_client(), SYNTHETIC, "http://example.org/x.pdf")  # fmt: skip


# -- wiring ---------------------------------------------------------------------------------


def test_a_missing_knowledge_directory_is_recorded(tmp_path: Path) -> None:
    registry = ServiceRegistry(settings=Settings(environment="test", log_json=False))
    install_knowledge(registry, tmp_path)
    assert registry.knowledge is None
    assert "cannot be read" in registry.problems["knowledge"]


def test_the_directory_can_be_configured(tmp_path: Path) -> None:
    assert knowledge_dir({"KNOWLEDGE_DIR": str(tmp_path)}) == tmp_path
    assert knowledge_dir({}) == DEFAULT_KNOWLEDGE_DIR
