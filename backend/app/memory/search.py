"""Frame search (owner: Student A).

STUB created in S0. Returns fake, contract-shaped data so Student B's
/api/ask and the dashboard work before the real database exists.
Student A replaces these bodies in A8; the function signatures are the
contract and must not change.
"""

from datetime import UTC, datetime, timedelta

from app.contracts import FrameDetail, FrameSummary, SearchHit


def _fake_frames() -> list[FrameDetail]:
    """Three fake frames captured 5, 30 and 90 seconds ago."""
    now = datetime.now(UTC)
    samples = [
        (1, 90, "EXIT", ["door"]),
        (2, 30, "Sortie de secours", ["person", "chair"]),
        (3, 5, "مخرج", ["door", "chair"]),
    ]
    frames = []
    for frame_id, seconds_ago, text, labels in samples:
        frames.append(
            FrameDetail(
                id=frame_id,
                captured_at=now - timedelta(seconds=seconds_ago),
                thumb_url=f"/media/thumbs/{frame_id}.jpg",
                image_url=f"/media/frames/{frame_id}.jpg",
                ocr_text=text,
                object_labels=labels,
                enhanced=False,
                width=640,
                height=480,
                sharpness=150.0,
                brightness=120.0,
                ocr_blocks=[],
                objects=[],
            )
        )
    return frames


def _summary(frame: FrameDetail) -> FrameSummary:
    return FrameSummary(**frame.model_dump(include=set(FrameSummary.model_fields)))


def search_frames(
    query: str,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 5,
) -> list[SearchHit]:
    """Best-matching frames for a text query, best first. STUB."""
    hits = [
        SearchHit(frame=_summary(f), score=round(0.9 - 0.2 * i, 2), matched_by=["text"])
        for i, f in enumerate(reversed(_fake_frames()))
    ]
    return hits[:limit]


def get_latest_frame(max_age_s: int = 10) -> FrameDetail | None:
    """Most recent stored frame if it is younger than max_age_s. STUB."""
    latest = _fake_frames()[-1]
    age = (datetime.now(UTC) - latest.captured_at).total_seconds()
    return latest if age <= max_age_s else None


def get_frame_image_path(frame_id: int) -> str:
    """Absolute path of a frame's JPEG. STUB (the file does not exist yet)."""
    from app.config import settings

    return str(settings.frames_path / f"{frame_id}.jpg")


def count_frames() -> int:
    """Number of frames currently stored. STUB."""
    return len(_fake_frames())


def list_fake_frames() -> list[FrameDetail]:
    """Used only by the S0 stub of api/frames.py. Student A removes it in A8."""
    return _fake_frames()
