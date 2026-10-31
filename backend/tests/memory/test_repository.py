"""A1 done-test: insert a frame with both vectors and read it back.

Run from backend/ (Postgres must be running):  pytest tests/memory -v
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.contracts import DetectedObject, FrameDetail, FrameSummary, OcrBlock
from app.memory import repository as repo

pytestmark = pytest.mark.usefixtures("clean_frames")


def _frame(seconds_ago: float, **overrides) -> repo.NewFrame:
    values = dict(
        captured_at=datetime.now(UTC) - timedelta(seconds=seconds_ago),
        image_path="frames/x.jpg",
        thumb_path="thumbs/x.jpg",
        width=640,
        height=480,
        sharpness=150.0,
        brightness=110.0,
    )
    values.update(overrides)
    return repo.NewFrame(**values)


def _unit_vector(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(512).astype(np.float32)
    return v / np.linalg.norm(v)


def test_insert_frame_with_both_vectors_and_read_back() -> None:
    image_emb, text_emb = _unit_vector(1), _unit_vector(2)
    new = _frame(
        3,
        enhanced=True,
        dhash=0xF0F0_F0F0_F0F0_F0F0,  # top bit set: checks the unsigned/signed round trip
        ocr_text="EXIT",
        ocr_blocks=[OcrBlock(text="EXIT", confidence=0.93, bbox=[10, 20, 110, 60])],
        objects=[
            DetectedObject(
                label="door", confidence=0.81, bbox=[200, 50, 440, 470],
                position="center", near=True,
            ),
            DetectedObject(
                label="chair", confidence=0.6, bbox=[0, 300, 120, 470],
                position="left", near=False,
            ),
        ],
        caption_text="Text: EXIT. Objects: door (center, near), chair (left)",
        image_emb=image_emb,
        text_emb=text_emb,
    )
    frame_id = repo.insert_frame(new)

    row = repo.get_frame(frame_id, with_embeddings=True)
    assert row is not None
    assert row.id == frame_id
    assert row.dhash == 0xF0F0_F0F0_F0F0_F0F0
    assert row.ocr_text == "EXIT"
    assert row.ocr_blocks[0].text == "EXIT"
    assert row.objects[0].position == "center" and row.objects[0].near is True
    assert row.object_labels == ["door", "chair"]
    assert np.allclose(row.image_emb, image_emb, atol=1e-6)
    assert np.allclose(row.text_emb, text_emb, atol=1e-6)

    # Converts to the exact contract models the API returns
    detail = row.to_detail()
    assert isinstance(detail, FrameDetail)
    assert detail.thumb_url == "/media/thumbs/x.jpg"
    assert detail.image_url == "/media/frames/x.jpg"
    assert isinstance(row.to_summary(), FrameSummary)

    # Without the flag the heavy vectors are not loaded
    assert repo.get_frame(frame_id).image_emb is None


def test_get_missing_frame_returns_none() -> None:
    assert repo.get_frame(999_999) is None


def test_reserved_id_is_used() -> None:
    frame_id = repo.reserve_frame_id()
    new = _frame(1, id=frame_id, image_path=f"frames/{frame_id}.jpg")
    assert repo.insert_frame(new) == frame_id
    # The next normal insert does not collide with the reserved id
    assert repo.insert_frame(_frame(0)) > frame_id


def test_list_frames_newest_first_with_paging_and_time_window() -> None:
    ids = [repo.insert_frame(_frame(s)) for s in (50, 40, 30, 20, 10)]  # oldest -> newest

    newest_first = [f.id for f in repo.list_frames()]
    assert newest_first == list(reversed(ids))

    page1 = repo.list_frames(limit=2)
    page2 = repo.list_frames(limit=2, before_id=page1[-1].id)
    assert [f.id for f in page1] == [ids[4], ids[3]]
    assert [f.id for f in page2] == [ids[2], ids[1]]

    now = datetime.now(UTC)
    window = repo.list_frames(since=now - timedelta(seconds=35), until=now - timedelta(seconds=15))
    assert [f.id for f in window] == [ids[3], ids[2]]


def test_count_oldest_and_retention_delete() -> None:
    assert repo.count_frames() == 0
    assert repo.oldest_frame_at() is None

    old_id = repo.insert_frame(_frame(3600, image_path="frames/old.jpg"))
    repo.insert_frame(_frame(5))
    assert repo.count_frames() == 2
    assert repo.oldest_frame_at() < datetime.now(UTC) - timedelta(minutes=59)

    deleted = repo.delete_frames_older_than(datetime.now(UTC) - timedelta(minutes=30))
    assert [d.id for d in deleted] == [old_id]
    assert deleted[0].image_path == "frames/old.jpg"
    assert repo.count_frames() == 1
