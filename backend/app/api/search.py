"""GET /api/search (owner: Student A, task A8).

The dashboard Search page: same ranking as the assistant's evidence search
(memory/search.py), but with up to 50 results and an explicit 503 when the
database is down (the assistant gets an empty list instead).

When the API starts, the multilingual text model (~30 s from disk) is loaded in a
background thread, so the first question is not slow. The API answers meanwhile.
"""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, FastAPI, Query

from app.api.frames import database_unavailable
from app.contracts import SearchHit
from app.db import DB_ERRORS
from app.memory.search import rank_frames, warm_up


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runs with uvicorn; not in the tests (they never start the app's lifespan)
    threading.Thread(target=warm_up, name="search-warm-up", daemon=True).start()
    yield


router = APIRouter(prefix="/api/search", tags=["search (Student A)"], lifespan=lifespan)


@router.get("", response_model=list[SearchHit])
def search(
    q: str = Query(..., min_length=1),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(10, ge=1, le=50),
) -> list[SearchHit]:
    try:
        return rank_frames(q, since=since, until=until, limit=limit)
    except DB_ERRORS as error:
        raise database_unavailable(error) from error
