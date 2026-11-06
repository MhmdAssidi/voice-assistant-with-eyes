"""GET /api/frames and GET /api/frames/{id} (owner: Student A, task A8).

The dashboard Timeline (newest first, infinite scroll with before_id) and FrameDetail.
The images themselves are served at /media/... (thumb_url, image_url).
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.contracts import FrameDetail, FrameSummary
from app.db import DB_ERRORS
from app.memory import repository as repo

router = APIRouter(prefix="/api/frames", tags=["frames (Student A)"])


def database_unavailable(error: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"Database unavailable: {type(error).__name__}")


@router.get("", response_model=list[FrameSummary])
def list_frames(
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = None,
) -> list[FrameSummary]:
    try:
        rows = repo.list_frames(since=since, until=until, limit=limit, before_id=before_id)
    except DB_ERRORS as error:
        raise database_unavailable(error) from error
    return [row.to_summary() for row in rows]


@router.get("/{frame_id}", response_model=FrameDetail)
def get_frame(frame_id: int) -> FrameDetail:
    try:
        row = repo.get_frame(frame_id)
    except DB_ERRORS as error:
        raise database_unavailable(error) from error
    if row is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    return row.to_detail()
