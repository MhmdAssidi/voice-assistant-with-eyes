"""POST /api/ask (owner: Student B).

audio (or text) -> speech-to-text (B6) -> evidence frames + VLM answer (B7).
B8 adds the honesty rules, B11 saves each Q&A and broadcasts it.
"""

import io
import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.assistant import answer, stt
from app.assistant.i18n import NOT_HEARD, phrase
from app.config import settings
from app.contracts import AskResponse

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

    # Search + VLM call are blocking (disk, network): also in a worker thread.
    result = await run_in_threadpool(answer.answer_question, question, language)
    timings.update(result.timings_ms)
    timings["total"] = _ms_since(started)

    return AskResponse(
        id=1,  # B11 replaces this with the qa_log row id
        question=question,
        language=language,
        answer=result.answer,
        confident=result.confident,
        evidence=result.evidence,
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
