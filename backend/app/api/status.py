"""GET /api/status (owner: Student B, S0 + B11).

Combines the latest ingest_status from Student A's worker, the frame count,
and the time of the last question. The worker posts ingest_status every 2 s;
if nothing arrived for STALE_AFTER_S, the stream and the worker are reported
as down (the worker may have crashed without saying so).
"""

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.assistant import qa_repository
from app.contracts import SystemStatus
from app.memory.search import count_frames
from app.realtime.hub import hub

router = APIRouter(prefix="/api/status", tags=["status (Student B)"])

STALE_AFTER_S = 5.0


@router.get("", response_model=SystemStatus)
async def get_status() -> SystemStatus:
    ingest = hub.last_ingest_status.data if hub.last_ingest_status else {}
    fresh = hub.ingest_is_fresh(STALE_AFTER_S)
    last_question_at = hub.last_question_at or await run_in_threadpool(
        qa_repository.last_asked_at  # after an API restart, the hub knows nothing yet
    )
    return SystemStatus(
        stream_connected=fresh and bool(ingest.get("stream_connected", False)),
        ingest_running=fresh and bool(ingest.get("ingest_running", False)),
        frames_seen=int(ingest.get("frames_seen", 0)),
        frames_kept=int(ingest.get("frames_kept", 0)),
        frame_count=count_frames(),
        last_frame_at=hub.last_frame_at,
        avg_process_ms=int(ingest.get("avg_process_ms", 0)),
        last_question_at=last_question_at,
    )
