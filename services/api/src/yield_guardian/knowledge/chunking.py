"""Split document Markdown (OCR output, one string per page) into searchable chunks that keep
their provenance: the source, the page and the section heading each chunk comes from."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

MAX_CHARS = 1200
"""About 200 words: a passage an engineer can read in the chat's citation card."""

_HEADING = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
_SPACE = re.compile(r"[ \t]+")


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    source_id: str
    location: str
    """Where the text is, for a reader: "p. 3, section 2.1 Edge defects"."""
    text: str


@dataclass(frozen=True, slots=True)
class _Block:
    page: int
    section: str | None
    text: str


def _location(page: int | None, section: str | None) -> str:
    parts = []
    if page is not None:
        parts.append(f"p. {page + 1}")
    if section:
        parts.append(f"section {section[:120]}")
    return ", ".join(parts) or "whole document"


def _blocks(pages: Iterable[tuple[int, str]]) -> list[_Block]:
    """Paragraphs with the page and the latest heading above them."""
    blocks: list[_Block] = []
    section: str | None = None
    for page, markdown in pages:
        paragraph: list[str] = []
        for line in [*markdown.splitlines(), ""]:
            heading = _HEADING.match(line)
            if heading or not line.strip():
                text = _SPACE.sub(" ", " ".join(paragraph)).strip()
                if text:
                    blocks.append(_Block(page, section, text))
                paragraph = []
                if heading:
                    section = _SPACE.sub(" ", heading.group("title")).strip()
            else:
                paragraph.append(line.strip())
    return blocks


def _pieces(text: str, limit: int) -> list[str]:
    """A paragraph longer than ``limit``, cut at sentence ends (or hard, as a last resort)."""
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    current = ""
    for sentence in _SENTENCE.split(text):
        while len(sentence) > limit:
            if current:
                out.append(current)
                current = ""
            out.append(sentence[:limit])
            sentence = sentence[limit:]
        if current and len(current) + 1 + len(sentence) > limit:
            out.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        out.append(current)
    return out


def chunk_id(source_id: str, index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()[:8]
    return f"{source_id}-{index:04d}-{digest}"


def chunk_markdown(
    source_id: str, pages: Iterable[tuple[int, str]], *, max_chars: int = MAX_CHARS
) -> list[Chunk]:
    """Chunks of at most ``max_chars`` characters that never cross a page or a section, so
    every chunk has one location."""
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    chunks: list[Chunk] = []
    current: list[str] = []
    key: tuple[int, str | None] | None = None

    def emit() -> None:
        if current and key is not None:
            text = "\n\n".join(current)
            chunks.append(Chunk(chunk_id(source_id, len(chunks), text), source_id, _location(*key), text))  # fmt: skip
        current.clear()

    for block in _blocks(pages):
        block_key = (block.page, block.section)
        for piece in _pieces(block.text, max_chars):
            size = sum(len(p) + 2 for p in current) + len(piece)
            if block_key != key or size > max_chars:
                emit()
                key = block_key
            current.append(piece)
    emit()
    return chunks
