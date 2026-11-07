"""The answer pipeline (owner: Student B, tasks B7-B8).

question -> evidence frames (live snapshot for "now" questions + latest stored frame +
best search hits) -> prompt -> VLM -> honesty rules (uncertainty.py) -> answer.
Every stage is timed; the times go back to the phone and the dashboard.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.assistant import prompts, uncertainty
from app.assistant.i18n import NO_EVIDENCE, VLM_UNAVAILABLE, phrase
from app.assistant.live_view import LiveFrame
from app.assistant.vlm import VlmError, get_provider
from app.contracts import Evidence, FrameSummary
from app.memory import search

log = logging.getLogger("uvicorn.error")

MAX_IMAGES = 3  # more images = slower and not more accurate for short questions
SEARCH_WINDOW = timedelta(minutes=10)  # "what did that sign say?" means recently
# "What is in front of me?" is about NOW: frames from minutes ago would describe a scene
# the user has left (tested: old laptop frames answered a question about a cigarette box).
LIVE_SEARCH_WINDOW = timedelta(seconds=60)
# The latest frame may be this old: speech-to-text alone takes 8-17 s on the laptop CPU,
# so the frame from when the user STARTED asking is often 15-25 s old at search time.
LATEST_MAX_AGE_S = 30


@dataclass
class EvidenceFrame:
    frame: FrameSummary
    score: float  # search score; 1.0 for the latest frame
    is_latest: bool
    objects: list[str]  # with positions when known, e.g. "door (center, near)"
    jpeg: bytes | None  # None if the image file is missing (deleted by retention)
    analysed: bool = True  # False for the live snapshot: no OCR/objects, the model reads it


@dataclass
class AnswerResult:
    answer: str
    confident: bool
    evidence: list[Evidence]
    timings_ms: dict[str, int] = field(default_factory=dict)


def gather_evidence(
    question: str, now: datetime | None = None, live: LiveFrame | None = None
) -> list[EvidenceFrame]:
    """Newest view first, then the best search hits, without duplicates, max 3.

    For live-view questions the newest view is the live snapshot taken when the
    question arrived (if it is usable), and the search only looks at the last
    minute; other questions ("what did that sign say?") look at the last 10 minutes.
    """
    now = now or datetime.now(UTC)
    is_live = uncertainty.is_live_question(question)
    window = LIVE_SEARCH_WINDOW if is_live else SEARCH_WINDOW
    chosen: list[EvidenceFrame] = []

    if is_live and live is not None and live.usable:
        snapshot = FrameSummary(
            id=0,  # not a stored frame
            captured_at=live.captured_at,
            thumb_url=live.url,
            ocr_text="",
            object_labels=[],
            enhanced=False,
        )
        chosen.append(EvidenceFrame(snapshot, 1.0, True, [], live.jpeg, analysed=False))

    latest = search.get_latest_frame(max_age_s=LATEST_MAX_AGE_S)
    if latest is not None:
        objects = [
            f"{o.label} ({o.position}{', near' if o.near else ''})" for o in latest.objects
        ] or latest.object_labels
        summary = FrameSummary(**latest.model_dump(include=set(FrameSummary.model_fields)))
        is_newest = not chosen  # the live snapshot, when present, is newer
        chosen.append(EvidenceFrame(summary, 1.0, is_newest, objects, _read_jpeg(latest.id)))

    for hit in search.search_frames(question, since=now - window, limit=5):
        if len(chosen) >= MAX_IMAGES:
            break
        if any(e.frame.id == hit.frame.id for e in chosen):
            continue
        jpeg = _read_jpeg(hit.frame.id)
        chosen.append(EvidenceFrame(hit.frame, hit.score, False, hit.frame.object_labels, jpeg))
    return chosen


def answer_question(question: str, language: str, live: LiveFrame | None = None) -> AnswerResult:
    timings: dict[str, int] = {}

    if uncertainty.is_live_question(question) and live is not None and not live.usable:
        # The camera sees nothing useful right now (covered, too dark, too close):
        # say so, instead of describing an older scene the user may have left.
        timings.update(search=0, vlm=0)
        seen = [Evidence(frame_id=0, captured_at=live.captured_at, thumb_url=live.url, score=0.0)]
        log.info("answer [%s]: live view not usable (%s)", language, live.reason)
        return AnswerResult(phrase(NO_EVIDENCE, language), False, seen, timings)

    started = time.perf_counter()
    evidence = gather_evidence(question, live=live)
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
            ocr_text=e.frame.ocr_text if e.analysed else None,
            objects=e.objects if e.analysed else None,
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

    # B8: honesty rules in code (weak evidence -> "I'm not sure", never "safe", max 2 sentences)
    text, confident = uncertainty.apply_rules(
        reply.answer,
        reply.confident,
        language,
        question,
        hit_scores=[e.score for e in evidence if not e.is_latest],
        has_latest=any(e.is_latest for e in evidence),
    )
    log.info(
        "answer [%s, %d images, %d ms, model confident=%s -> %s]: %r%s",
        language, len(images), timings["vlm"], reply.confident, confident, text,
        "" if text == reply.answer.strip() else f" (model said: {reply.answer!r})",
    )
    return AnswerResult(text, confident, evidence_out, timings)


def _read_jpeg(frame_id: int) -> bytes | None:
    path = Path(search.get_frame_image_path(frame_id))
    return path.read_bytes() if path.is_file() else None


def _ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
