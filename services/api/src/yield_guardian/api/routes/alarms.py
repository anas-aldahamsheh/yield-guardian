from typing import Annotated

from fastapi import APIRouter, Query

from yield_guardian.api.deps import Alarms
from yield_guardian.api.problems import problem_responses
from yield_guardian.contracts.line import AlarmKind, AlarmPage, AlarmStatus

router = APIRouter(tags=["alarms"])


@router.get("/alarms", operation_id="list_alarms", responses=problem_responses(503))
async def list_alarms(
    alarms: Alarms,
    status: AlarmStatus | None = None,
    kind: AlarmKind | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> AlarmPage:
    """SECOM unit alarms (AL-<unit>-<kind>) over every unit, newest first."""
    return await alarms.list_alarms(status=status, kind=kind, cursor=cursor, limit=limit)
