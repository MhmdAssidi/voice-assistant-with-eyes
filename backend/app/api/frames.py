"""GET /api/frames and GET /api/frames/{id} (owner: Student A).

STUB created in S0: serves the fake frames from memory/search.py.
Student A replaces it with real database queries in A8.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.contracts import FrameDetail, FrameSummary
from app.memory.search import _summary, list_fake_frames

router = APIRouter(prefix="/api/frames", tags=["frames (Student A)"])


@router.get("", response_model=list[FrameSummary])
def list_frames(
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = None,
) -> list[FrameSummary]:
    frames = sorted(list_fake_frames(), key=lambda f: f.captured_at, reverse=True)
    return [_summary(f) for f in frames][:limit]


@router.get("/{frame_id}", response_model=FrameDetail)
def get_frame(frame_id: int) -> FrameDetail:
    for frame in list_fake_frames():
        if frame.id == frame_id:
            return frame
    raise HTTPException(status_code=404, detail="Frame not found")
