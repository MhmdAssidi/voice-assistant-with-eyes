"""POST /api/ask (owner: Student B).

STUB created in S0: accepts audio OR text and returns a fake AskResponse
built from the stub search, so the phone and dashboard can be wired up
now. Replaced by the real STT + retrieval + VLM pipeline in B6-B8.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.contracts import AskResponse, Evidence
from app.memory.search import search_frames

router = APIRouter(prefix="/api/ask", tags=["ask (Student B)"])


@router.post("", response_model=AskResponse)
async def ask(
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    lang_hint: str | None = Form(None),
) -> AskResponse:
    if audio is None and not text:
        raise HTTPException(status_code=422, detail="Send either 'audio' or 'text'.")

    question = text or "(audio received; speech-to-text comes in B6)"
    language = lang_hint if lang_hint in ("en", "fr", "ar") else "en"
    since = datetime.now(UTC) - timedelta(minutes=10)
    hits = search_frames(question, since=since, limit=3)

    return AskResponse(
        id=1,
        question=question,
        language=language,
        answer="This is a test answer from the S0 stub. I'm not sure what is in front of you yet.",
        confident=False,
        evidence=[
            Evidence(
                frame_id=h.frame.id,
                captured_at=h.frame.captured_at,
                thumb_url=h.frame.thumb_url,
                score=h.score,
            )
            for h in hits
        ],
        timings_ms={"stt": 0, "search": 0, "vlm": 0, "total": 0},
    )
