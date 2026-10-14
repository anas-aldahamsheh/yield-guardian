"""Ingest open-access documents into the knowledge index.

A document goes through MinerU OCR on the Token Factory (``POST /v1/ocr``, billed per page),
or is given as Markdown already, then is chunked with provenance (:mod:`.chunking`) and added
to a :class:`~yield_guardian.knowledge.search.FullTextIndex`. OCR is an explicit, offline
curation step run by a person (never at startup, never in tests against the endpoint); its
Markdown is stored so the product serves only text that a person has read.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from yield_guardian.contracts.knowledge import KnowledgeSource, PatternCauses
from yield_guardian.knowledge.chunking import Chunk, chunk_markdown
from yield_guardian.knowledge.search import FullTextIndex
from yield_guardian.llm.client import OcrResult


class DocumentOcr(Protocol):
    """What ingestion needs from the Token Factory client (``TokenFactoryClient.ocr``)."""

    async def ocr(
        self, *, document_url: str, pages: str | None = None, model: str = "MinerU2.5-Pro"
    ) -> OcrResult: ...


@dataclass(frozen=True, slots=True)
class IngestedDocument:
    source: KnowledgeSource
    pages: tuple[tuple[int, str], ...]
    chunks: tuple[Chunk, ...]


async def ocr_pages(
    ocr: DocumentOcr, document_url: str, *, pages: str | None = None
) -> tuple[tuple[int, str], ...]:
    """The Markdown of each page MinerU read, in page order."""
    if not document_url.startswith("https://"):
        raise ValueError("documents are fetched by the OCR service over https only")
    result = await ocr.ocr(document_url=document_url, pages=pages)
    return tuple(sorted((page.index, page.markdown) for page in result.pages))


def ingest_markdown(
    index: FullTextIndex, source: KnowledgeSource, pages: Sequence[tuple[int, str]]
) -> IngestedDocument:
    chunks = tuple(chunk_markdown(source.source_id, pages))
    index.add(source, chunks)
    return IngestedDocument(source, tuple(pages), chunks)


async def ingest_document(
    index: FullTextIndex,
    ocr: DocumentOcr,
    source: KnowledgeSource,
    document_url: str,
    *,
    pages: str | None = None,
) -> IngestedDocument:
    """OCR a document with MinerU, chunk it and index it."""
    if not source.open_access:
        raise ValueError(f"{source.source_id} is not open access; only open sources are ingested")
    return ingest_markdown(index, source, await ocr_pages(ocr, document_url, pages=pages))


def save_markdown(directory: Path, document: IngestedDocument) -> Path:
    """Store an ingested document as reviewed Markdown with its source as a JSON header line."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{document.source.source_id}.md"
    header = json.dumps(document.source.model_dump(mode="json"), ensure_ascii=False)
    body = "".join(f"\n<!-- page {index} -->\n{markdown}\n" for index, markdown in document.pages)
    path.write_text(f"<!-- source {header} -->\n{body}", encoding="utf-8")
    return path


def load_markdown(path: Path) -> tuple[KnowledgeSource, tuple[tuple[int, str], ...]]:
    """Read a file written by :func:`save_markdown`."""
    text = path.read_text(encoding="utf-8")
    first, _, rest = text.partition("\n")
    if not (first.startswith("<!-- source ") and first.endswith(" -->")):
        raise ValueError(f"{path.name}: the first line must be the source header")
    source = KnowledgeSource.model_validate_json(first[len("<!-- source ") : -len(" -->")])
    pages: list[tuple[int, str]] = []
    for part in rest.split("\n<!-- page ")[1:]:
        number, _, markdown = part.partition(" -->\n")
        pages.append((int(number), markdown.rstrip("\n")))
    return source, tuple(pages)


def quote_chunks(causes: PatternCauses) -> dict[str, list[Chunk]]:
    """Each verified quote of the pattern-cause table as a chunk of its source, so the search
    serves exact text read in the sources, with its location."""
    by_source: dict[str, list[Chunk]] = {}
    for cause in causes.causes:
        for quote in cause.quotes:
            chunks = by_source.setdefault(quote.source_id, [])
            text = quote.quote
            chunk = Chunk(
                chunk_id=f"{quote.source_id}-q{len(chunks):03d}",
                source_id=quote.source_id,
                location=quote.location,
                text=text,
            )
            if all(c.text != text for c in chunks):
                chunks.append(chunk)
    return by_source
