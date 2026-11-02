"""The answer pipeline (owner: Student B, task B7).

question -> evidence frames (latest + best search hits) -> prompt -> VLM -> answer.
Every stage is timed; the times go back to the phone and the dashboard.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.assistant import prompts
from app.assistant.i18n import NO_EVIDENCE, VLM_UNAVAILABLE, phrase
from app.assistant.vlm import VlmError, get_provider
from app.contracts import Evidence, FrameSummary
from app.memory import search

log = logging.getLogger("uvicorn.error")

MAX_IMAGES = 3  # more images = slower and not more accurate for short questions
SEARCH_WINDOW = timedelta(minutes=10)  # "what did that sign say?" means recently
LATEST_MAX_AGE_S = 10  # older than this, the "latest frame" is not "in front of me"


@dataclass
class EvidenceFrame:
    frame: FrameSummary
    score: float  # search score; 1.0 for the latest frame
    is_latest: bool
    objects: list[str]  # with positions when known, e.g. "door (center, near)"
    jpeg: bytes | None  # None while frames are stubs (no file on disk)


@dataclass
class AnswerResult:
    answer: str
    confident: bool
    evidence: list[Evidence]
    timings_ms: dict[str, int] = field(default_factory=dict)


def gather_evidence(question: str, now: datetime | None = None) -> list[EvidenceFrame]:
    """Latest frame first, then the best search hits, without duplicates, max 3."""
    now = now or datetime.now(UTC)
    chosen: list[EvidenceFrame] = []

    latest = search.get_latest_frame(max_age_s=LATEST_MAX_AGE_S)
    if latest is not None:
        objects = [
            f"{o.label} ({o.position}{', near' if o.near else ''})" for o in latest.objects
        ] or latest.object_labels
        summary = FrameSummary(**latest.model_dump(include=set(FrameSummary.model_fields)))
        chosen.append(EvidenceFrame(summary, 1.0, True, objects, _read_jpeg(latest.id)))

    for hit in search.search_frames(question, since=now - SEARCH_WINDOW, limit=5):
        if len(chosen) >= MAX_IMAGES:
            break
        if any(e.frame.id == hit.frame.id for e in chosen):
            continue
        jpeg = _read_jpeg(hit.frame.id)
        chosen.append(EvidenceFrame(hit.frame, hit.score, False, hit.frame.object_labels, jpeg))
    return chosen


def answer_question(question: str, language: str) -> AnswerResult:
    timings: dict[str, int] = {}

    started = time.perf_counter()
    evidence = gather_evidence(question)
    timings["search"] = _ms_since(started)
    evidence_out = [
        Evidence(
            frame_id=e.frame.id,
            captured_at=e.frame.captured_at,
            thumb_url=e.frame.thumb_url,
            score=e.score,
        )
        for e in evidence
    ]

    if not evidence:
        # Nothing stored yet (camera off, or worker not running): don't ask the model to guess.
        timings["vlm"] = 0
        return AnswerResult(phrase(NO_EVIDENCE, language), False, [], timings)

    now = datetime.now(UTC)
    prompt_images = [
        prompts.PromptImage(
            age_s=max(0, int((now - e.frame.captured_at).total_seconds())),
            ocr_text=e.frame.ocr_text,
            objects=e.objects,
            is_latest=e.is_latest,
            has_image=e.jpeg is not None,
        )
        for e in evidence
    ]
    images = [e.jpeg for e in evidence if e.jpeg is not None]

    started = time.perf_counter()
    try:
        reply = get_provider().generate(
            prompts.system_prompt(language),
            prompts.user_prompt(question, prompt_images),
            images,
        )
    except VlmError as error:
        log.warning("VLM unavailable: %s", error)
        timings["vlm"] = _ms_since(started)
        return AnswerResult(phrase(VLM_UNAVAILABLE, language), False, evidence_out, timings)
    timings["vlm"] = _ms_since(started)
    log.info(
        "answer [%s, %d images, %d ms, confident=%s]: %r",
        language, len(images), timings["vlm"], reply.confident, reply.answer,
    )
    # B8 adds the honesty rules here (score threshold, "I'm not sure", never "safe").
    return AnswerResult(reply.answer.strip(), reply.confident, evidence_out, timings)


def _read_jpeg(frame_id: int) -> bytes | None:
    path = Path(search.get_frame_image_path(frame_id))
    return path.read_bytes() if path.is_file() else None


def _ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
