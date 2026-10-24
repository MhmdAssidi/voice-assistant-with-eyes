"""Shared API contract v1.0 (SHARED file).

These Pydantic models ARE the agreement between Student A and Student B.
dashboard/src/types.ts mirrors them field for field.
Change only through a `contract/...` pull request approved by both students.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Language = Literal["en", "fr", "ar"]


class DetectedObject(BaseModel):
    label: str  # English class name
    confidence: float  # 0..1
    bbox: list[int]  # [x1, y1, x2, y2] in pixels
    position: Literal["left", "center", "right"]
    near: bool  # box area > 25% of the frame


class OcrBlock(BaseModel):
    text: str
    confidence: float
    bbox: list[int]


class FrameSummary(BaseModel):
    id: int
    captured_at: datetime
    thumb_url: str  # e.g. "/media/thumbs/123.jpg"
    ocr_text: str  # "" if none
    object_labels: list[str]
    enhanced: bool


class FrameDetail(FrameSummary):
    image_url: str
    width: int
    height: int
    sharpness: float
    brightness: float
    ocr_blocks: list[OcrBlock]
    objects: list[DetectedObject]


class SearchHit(BaseModel):
    frame: FrameSummary
    score: float  # 0..1, higher is better
    matched_by: list[Literal["image", "text", "ocr", "time"]]


class Evidence(BaseModel):
    frame_id: int
    captured_at: datetime
    thumb_url: str
    score: float


class AskResponse(BaseModel):
    id: int
    question: str
    language: Language
    answer: str  # 1-2 short sentences, ready to speak
    confident: bool
    evidence: list[Evidence]
    timings_ms: dict[str, int]  # keys: stt, search, vlm, total


class QaRecord(AskResponse):
    asked_at: datetime


class SystemStatus(BaseModel):
    stream_connected: bool
    ingest_running: bool
    frames_seen: int
    frames_kept: int
    frame_count: int  # rows currently in the database
    last_frame_at: datetime | None
    avg_process_ms: int
    last_question_at: datetime | None


EventType = Literal["frame_stored", "ingest_status", "question_answered", "warning"]


class Event(BaseModel):
    type: EventType
    ts: datetime
    data: dict
