"""Full-text search over the knowledge chunks.

:class:`FullTextIndex` is the protocol; :class:`InMemoryFullTextIndex` ranks with Okapi BM25
(k1 1.2, b 0.75) over lower-cased word stems. The corpus is small (curated open-access sources),
so an in-memory index answers in microseconds; a PostgreSQL ``tsvector`` index can implement the
same protocol later without changing any caller.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from yield_guardian.contracts.knowledge import KnowledgeHit, KnowledgeSource
from yield_guardian.knowledge.chunking import Chunk

METHOD = "In-memory full-text search, Okapi BM25 (k1 1.2, b 0.75) over word stems"
SNIPPET_CHARS = 320
_WORD = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "which",
        "with",
        "what",
        "why",
        "how",
        "do",
        "does",
        "can",
        "could",
        "would",
        "should",
        "than",
        "then",
        "there",
        "these",
        "those",
        "into",
        "about",
        "over",
        "under",
        "between",
        "also",
        "not",
        "no",
    ]
)


def stem(word: str) -> str:
    """A light suffix stripper: enough to match "rings" with "ring", "scratches" with
    "scratch", and "caused", "causes" and "cause" with each other."""
    for suffix, keep in (("ies", "y"), ("sses", "ss"), ("ches", "ch"), ("shes", "sh"), ("ing", ""), ("ed", ""), ("es", "e"), ("s", "")):  # fmt: skip
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: len(word) - len(suffix)] + keep
            break
    return word[:-1] if word.endswith("e") and len(word) > 3 else word


def terms(text: str) -> list[str]:
    words: list[str] = []
    for match in _WORD.finditer(text.lower()):
        word = match.group(0)
        if "-" in word or "'" in word:
            words.append(word)  # the compound as written ("edge-ring"), then its parts
            parts = re.split(r"[-']", word)
        else:
            parts = [word]
        words.extend(stem(part) for part in parts if part not in _STOP and len(part) > 1)
    return words


class FullTextIndex(Protocol):
    def add(self, source: KnowledgeSource, chunks: Iterable[Chunk]) -> int: ...

    def search(self, query: str, *, limit: int = 5) -> list[KnowledgeHit]: ...

    @property
    def method(self) -> str: ...


@dataclass(frozen=True, slots=True)
class _Doc:
    chunk: Chunk
    source: KnowledgeSource
    counts: Counter[str]
    length: int


def snippet(text: str, query_terms: Sequence[str], size: int = SNIPPET_CHARS) -> str:
    """The window of ``text`` with the most query terms, starting a little before the first
    of them and cut at word boundaries; the text itself is never changed."""
    if len(text) <= size:
        return text
    wanted = set(query_terms)
    words = list(re.finditer(r"\S+", text))
    hits = [w for w in words if stem(re.sub(r"[^\w-]", "", w.group(0).lower())) in wanted]
    lead = size // 5
    best_start, best_score = 0, -1
    for hit in hits:
        start = max(0, hit.start() - lead)
        score = sum(1 for h in hits if start <= h.start() and h.end() <= start + size)
        if score > best_score:
            best_start, best_score = start, score
    if best_start > 0:
        best_start = next((w.start() for w in words if w.start() >= best_start), best_start)
    end = min(len(text), best_start + size)
    if end < len(text):
        cut = text.rfind(" ", best_start, end)
        end = cut if cut > best_start + size // 2 else end
    prefix = "\u2026" if best_start > 0 else ""
    suffix = "\u2026" if end < len(text) else ""
    return prefix + text[best_start:end].strip() + suffix


class InMemoryFullTextIndex:
    def __init__(self, *, k1: float = 1.2, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: list[_Doc] = []
        self._ids: set[str] = set()
        self._df: Counter[str] = Counter()

    @property
    def method(self) -> str:
        return METHOD

    def __len__(self) -> int:
        return len(self._docs)

    def add(self, source: KnowledgeSource, chunks: Iterable[Chunk]) -> int:
        added = 0
        for chunk in chunks:
            if chunk.source_id != source.source_id:
                raise ValueError(f"chunk {chunk.chunk_id} belongs to {chunk.source_id}")
            if chunk.chunk_id in self._ids:
                continue
            words = terms(chunk.text)
            counts = Counter(words)
            self._docs.append(_Doc(chunk, source, counts, len(words)))
            self._ids.add(chunk.chunk_id)
            self._df.update(counts.keys())
            added += 1
        return added

    def search(self, query: str, *, limit: int = 5) -> list[KnowledgeHit]:
        wanted = list(dict.fromkeys(terms(query)))
        if not wanted or not self._docs:
            return []
        n = len(self._docs)
        average = sum(d.length for d in self._docs) / n or 1.0
        scored: list[tuple[float, int, _Doc]] = []
        for position, doc in enumerate(self._docs):
            score = 0.0
            for term in wanted:
                tf = doc.counts.get(term, 0)
                if not tf:
                    continue
                idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * doc.length / average))  # fmt: skip
                score += idf * norm
            if score > 0:
                scored.append((score, position, doc))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            KnowledgeHit(
                chunk_id=doc.chunk.chunk_id,
                source=doc.source,
                location=doc.chunk.location,
                snippet=snippet(doc.chunk.text, wanted),
                rank=round(score, 4),
            )
            for score, _, doc in scored[:limit]
        ]
