"""GET /api/questions (owner: Student B).

STUB created in S0: one fake Q&A record. Replaced by the qa_log table in B11.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Query

from app.contracts import QaRecord

router = APIRouter(prefix="/api/questions", tags=["questions (Student B)"])


@router.get("", response_model=list[QaRecord])
def list_questions(limit: int = Query(50, ge=1, le=200)) -> list[QaRecord]:
    fake = QaRecord(
        id=1,
        asked_at=datetime.now(UTC),
        question="What's in front of me?",
        language="en",
        answer="I'm not sure. This is fake data from the S0 stub.",
        confident=False,
        evidence=[],
        timings_ms={"stt": 0, "search": 0, "vlm": 0, "total": 0},
    )
    return [fake][:limit]
