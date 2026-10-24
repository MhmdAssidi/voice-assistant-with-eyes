"""GET /api/status (owner: Student B).

S0 version: combines the latest ingest_status event (if Student A's worker
sent one) with count_frames(). Completed in B11.
"""

from fastapi import APIRouter

from app.contracts import SystemStatus
from app.memory.search import count_frames
from app.realtime.hub import hub

router = APIRouter(prefix="/api/status", tags=["status (Student B)"])


@router.get("", response_model=SystemStatus)
def get_status() -> SystemStatus:
    ingest = hub.last_ingest_status.data if hub.last_ingest_status else {}
    return SystemStatus(
        stream_connected=bool(ingest.get("stream_connected", False)),
        ingest_running=bool(ingest.get("ingest_running", False)),
        frames_seen=int(ingest.get("frames_seen", 0)),
        frames_kept=int(ingest.get("frames_kept", 0)),
        frame_count=count_frames(),
        last_frame_at=None,
        avg_process_ms=int(ingest.get("avg_process_ms", 0)),
        last_question_at=None,
    )
