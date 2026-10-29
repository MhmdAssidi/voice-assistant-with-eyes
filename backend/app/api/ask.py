"""POST /api/ask (owner: Student B).

B6: real speech-to-text (faster-whisper) for audio questions.
Still a STUB after that: the answer is fake until the retrieval + VLM
pipeline arrives in B7-B8.
"""

import io
import logging
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.assistant import stt
from app.assistant.i18n import NOT_HEARD, phrase
from app.config import settings
from app.contracts import AskResponse, Evidence
from app.memory.search import search_frames

router = APIRouter(prefix="/api/ask", tags=["ask (Student B)"])
log = logging.getLogger("uvicorn.error")  # shows up in the uvicorn terminal


@router.post("", response_model=AskResponse)
async def ask(
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    lang_hint: str | None = Form(None),
) -> AskResponse:
    if audio is None and not text:
        raise HTTPException(status_code=422, detail="Send either 'audio' or 'text'.")

    started = time.perf_counter()
    timings: dict[str, int] = {"stt": 0, "search": 0, "vlm": 0}

    if audio is not None:
        data = await audio.read()
        try:
            # Whisper is CPU-heavy: run it in a worker thread so the API keeps
            # answering other requests (health checks, dashboard) meanwhile.
            transcript = await run_in_threadpool(stt.transcribe, io.BytesIO(data), lang_hint)
        except Exception as error:  # undecodable or empty file
            raise HTTPException(
                status_code=400, detail=f"Could not read the audio: {error}"
            ) from error
        timings["stt"] = _ms_since(started)
        question, language = transcript.text, transcript.language
        log.info(
            "heard [%s, detected %s p=%.2f, %.1f s audio, %d ms]: %r",
            language, transcript.detected_language, transcript.language_probability,
            transcript.duration_s, timings["stt"], question,
        )
        if settings.save_question_audio:
            _save_question_audio(data, language)
        if not question:
            return _not_heard(language, timings, started)
    else:
        question = text or ""
        language = stt.fallback_language(lang_hint)

    search_started = time.perf_counter()
    since = datetime.now(UTC) - timedelta(minutes=10)
    hits = search_frames(question, since=since, limit=3)
    timings["search"] = _ms_since(search_started)

    timings["total"] = _ms_since(started)
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
        timings_ms=timings,
    )


def _not_heard(language: str, timings: dict[str, int], started: float) -> AskResponse:
    """Silence or noise only: ask the user to try again, in their language."""
    timings["total"] = _ms_since(started)
    return AskResponse(
        id=0,
        question="",
        language=language,  # type: ignore[arg-type]
        answer=phrase(NOT_HEARD, language),
        confident=False,
        evidence=[],
        timings_ms=timings,
    )


def _save_question_audio(data: bytes, language: str) -> None:
    folder = settings.frames_path.parent / "questions"  # data/questions (git-ignored)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now(UTC):%Y%m%d-%H%M%S}_{language}.m4a"
    path.write_bytes(data)
    log.info("saved question audio to %s", path)


def _ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
