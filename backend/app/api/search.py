"""GET /api/search (owner: Student A).

Thin wrapper around memory.search.search_frames(), which is still a stub.
"""

from datetime import datetime

from fastapi import APIRouter, Query

from app.contracts import SearchHit
from app.memory.search import search_frames

router = APIRouter(prefix="/api/search", tags=["search (Student A)"])


@router.get("", response_model=list[SearchHit])
def search(
    q: str = Query(..., min_length=1),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(10, ge=1, le=50),
) -> list[SearchHit]:
    return search_frames(q, since=since, until=until, limit=limit)
