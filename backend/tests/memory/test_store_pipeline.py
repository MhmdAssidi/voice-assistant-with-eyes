"""A7 tests: caption, image files, and the pipeline storing a kept frame end to end.

The AI models are replaced by small fakes, so these run fast (CI) but still use the
real quality filter, real JPEG files and the real database (va_test).
Run from backend/:  pytest tests/memory/test_store_pipeline.py -v
"""

from datetime import UTC, datetime, timedelta

import cv2
import numpy as np
import pytest

from app.config import settings
from app.contracts import DetectedObject, FrameSummary, OcrBlock
from app.ingest.grabber import GrabbedFrame
from app.ingest.pipeline import Pipeline
from app.memory import files
from app.memory import repository as repo
from app.memory.embeddings import DIM, build_caption
from app.vision.ocr import OcrResult
from tests.vision import scenes

DOOR = DetectedObject(label="door", confidence=0.8, bbox=[200, 40, 440, 470],
                      position="center", near=True)
CHAIR = DetectedObject(label="chair", confidence=0.7, bbox=[0, 300, 120, 470],
                       position="left", near=False)


# ---------- caption ----------

def test_caption_with_text_and_objects() -> None:
    caption = build_caption("SORTIE\nEXIT", [DOOR, CHAIR, CHAIR])
    assert caption == "Text: SORTIE EXIT. Objects: door (center, near), chair (left)"


def test_caption_parts_are_optional() -> None:
    assert build_caption("", [CHAIR]) == "Objects: chair (left)"
    assert build_caption("مخرج", []) == "Text: مخرج."
    assert build_caption("  ", []) == ""


# ---------- files ----------

@pytest.fixture
def frames_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "frames_dir", str(tmp_path))
    return tmp_path


def test_save_and_delete_frame_images(frames_dir) -> None:
    image_path, thumb_path = files.save_frame_images(7, scenes.exit_sign())
    assert (image_path, thumb_path) == ("frames/7.jpg", "thumbs/7.jpg")
    thumb = cv2.imread(str(frames_dir / thumb_path))
    assert thumb.shape[:2] == (240, 320)  # 640x480 -> 320 px wide, same aspect ratio
    assert cv2.imread(str(frames_dir / image_path)).shape[:2] == (480, 640)

    files.delete_files(image_path, thumb_path, "thumbs/does-not-exist.jpg")
    assert not (frames_dir / image_path).exists()


# ---------- the pipeline, end to end ----------

class FakeOcr:
    def read(self, image) -> OcrResult:
        return OcrResult("EXIT", [OcrBlock(text="EXIT", confidence=0.95, bbox=[90, 140, 300, 200])])


class FakeDetector:
    def detect(self, image) -> list[DetectedObject]:
        return [DOOR]


class FakeEmbedder:
    def embed_image(self, image) -> np.ndarray:
        return np.eye(DIM, dtype=np.float32)[0]

    def embed_text(self, text: str) -> np.ndarray:
        return np.eye(DIM, dtype=np.float32)[1]


class FakeNotifier:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def post(self, event_type: str, data: dict) -> bool:
        self.events.append((event_type, data))
        return True


@pytest.fixture
def pipeline(clean_frames, frames_dir):
    notifier = FakeNotifier()
    return Pipeline(ocr=FakeOcr(), detector=FakeDetector(), embedder=FakeEmbedder(),
                    notifier=notifier), notifier


def test_kept_frame_is_stored_with_files_row_and_event(pipeline, frames_dir) -> None:
    pipe, notifier = pipeline
    t0 = datetime.now(UTC)
    assert pipe.process(GrabbedFrame(1, t0, scenes.exit_sign())) is True

    rows = repo.list_frames()
    assert len(rows) == 1
    row = repo.get_frame(rows[0].id, with_embeddings=True)
    assert row.ocr_text == "EXIT"
    assert row.ocr_blocks[0].text == "EXIT"
    assert row.object_labels == ["door"]
    assert row.caption_text == "Text: EXIT. Objects: door (center, near)"
    assert (row.width, row.height) == (640, 480)
    assert row.sharpness > settings.sharpness_min and row.dhash is not None
    assert row.image_emb[0] == 1.0 and row.text_emb[1] == 1.0
    assert (frames_dir / row.image_path).exists() and (frames_dir / row.thumb_path).exists()

    # frame_stored event carries a contract FrameSummary
    event_type, data = notifier.events[0]
    assert event_type == "frame_stored"
    summary = FrameSummary(**data)
    assert summary.id == row.id
    assert summary.thumb_url == f"/media/thumbs/{row.id}.jpg"


def test_rejected_frames_store_nothing(pipeline) -> None:
    pipe, notifier = pipeline
    t0 = datetime.now(UTC)
    pipe.process(GrabbedFrame(1, t0, scenes.exit_sign()))  # kept
    assert pipe.process(GrabbedFrame(2, t0 + timedelta(seconds=1), scenes.exit_sign())) is False
    assert pipe.process(GrabbedFrame(3, t0, scenes.blurred(scenes.boxes(), 4))) is False
    assert repo.count_frames() == 1
    assert len(notifier.events) == 1


def test_database_error_leaves_no_orphan_files(pipeline, frames_dir, monkeypatch) -> None:
    pipe, _ = pipeline

    def broken_insert(frame):
        raise RuntimeError("database down")

    monkeypatch.setattr(repo, "insert_frame", broken_insert)
    with pytest.raises(RuntimeError):
        pipe.process(GrabbedFrame(1, datetime.now(UTC), scenes.exit_sign()))
    assert list(frames_dir.rglob("*.jpg")) == []
