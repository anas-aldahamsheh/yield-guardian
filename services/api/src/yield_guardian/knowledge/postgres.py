"""Knowledge search in PostgreSQL: the ``knowledge_chunks`` table (migration 0002) with an English
``tsvector`` column kept by the database and a GIN index.

The reviewed files in ``docs/knowledge`` stay the source of truth: :meth:`sync` replaces the
table's rows with the chunks loaded from them, in one transaction under an advisory lock, so
several API processes starting together leave one consistent copy. A query matches a chunk
that contains any of its words (after English stemming) and is ranked with ``ts_rank_cd``; the
snippet is an exact window of the stored text (never rewritten, no markup).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import bindparam, delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from yield_guardian.contracts.knowledge import KnowledgeHit, KnowledgeSource
from yield_guardian.db.tables import KnowledgeChunkRow
from yield_guardian.knowledge.chunking import Chunk
from yield_guardian.knowledge.search import query_words, snippet, terms

METHOD = (
    "PostgreSQL full-text search (English configuration, chunks with any query word), "
    "ranked by ts_rank_cd"
)
SYNC_LOCK_KEY = 0x59475F4B4E4F5700  # "YG_KNOW"

_SEARCH = text(
    """
    SELECT chunk_id, source, location, text, ts_rank_cd(search, query) AS rank
    FROM knowledge_chunks, to_tsquery('english'::regconfig, :query) AS query
    WHERE search @@ query
    ORDER BY rank DESC, position, chunk_id
    LIMIT :limit
    """
).bindparams(bindparam("query"), bindparam("limit"))


class PostgresFullTextIndex:
    """Implements :class:`~yield_guardian.knowledge.search.SearchIndex`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @property
    def method(self) -> str:
        return METHOD

    async def sync(self, documents: Sequence[tuple[KnowledgeSource, Sequence[Chunk]]]) -> int:
        """Replace the stored chunks with ``documents``; returns the number stored."""
        rows: dict[str, KnowledgeChunkRow] = {}
        for source, chunks in documents:
            payload = source.model_dump(mode="json")
            for chunk in chunks:
                if chunk.source_id != source.source_id:
                    raise ValueError(f"chunk {chunk.chunk_id} belongs to {chunk.source_id}")
                rows.setdefault(
                    chunk.chunk_id,
                    KnowledgeChunkRow(
                        chunk_id=chunk.chunk_id,
                        source_id=source.source_id,
                        source=payload,
                        position=len(rows),
                        location=chunk.location,
                        text=chunk.text,
                    ),
                )
        async with self._sessions.begin() as db:
            await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SYNC_LOCK_KEY})
            await db.execute(delete(KnowledgeChunkRow))
            db.add_all(rows.values())
        return len(rows)

    async def search_hits(self, query: str, *, limit: int = 5) -> list[KnowledgeHit]:
        words = query_words(query)
        if not words:
            return []
        async with self._sessions() as db:
            result = await db.execute(_SEARCH, {"query": " | ".join(words), "limit": limit})
            rows = result.all()
        wanted = terms(query)
        return [
            KnowledgeHit(
                chunk_id=row.chunk_id,
                source=KnowledgeSource.model_validate(row.source),
                location=row.location,
                snippet=snippet(row.text, wanted),
                rank=round(float(row.rank), 4),
            )
            for row in rows
        ]
