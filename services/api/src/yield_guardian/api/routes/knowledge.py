from typing import Annotated

from fastapi import APIRouter, Query

from yield_guardian.api.deps import Knowledge
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.knowledge import KnowledgeSearchResult, PatternCauses
from yield_guardian.contracts.wafer import WaferLabel

router = APIRouter(tags=["knowledge"])


@router.get("/knowledge/search", operation_id="search_knowledge", responses=problem_responses(503))
async def search_knowledge(
    knowledge: Knowledge,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> KnowledgeSearchResult:
    """Full-text search of the curated open-access literature."""
    return await knowledge.search(q, limit=limit)


@router.get(
    "/knowledge/patterns", operation_id="get_pattern_causes", responses=problem_responses(503)
)
async def get_pattern_causes(
    knowledge: Knowledge, label: WaferLabel | None = None
) -> PatternCauses:
    """Pattern-to-cause hypotheses with their sources."""
    return await knowledge.pattern_causes(label)
