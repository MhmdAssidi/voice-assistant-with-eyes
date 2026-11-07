"""A9 tests: old frames are forgotten (rows AND files), on the throw-away va_test database.

Run from backend/:  pytest tests/memory/test_retention.py -v
"""

import os
import time
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from app.config import settings
from app.memory import files, retention
from app.memory import repository as repo
from tests.vision import scenes


@pytest.fixture
def frames_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "frames_dir", str(tmp_path))
    return tmp_path


def store(minutes_ago: float) -> int:
    """A real stored frame: row + full JPEG + thumbnail, like the pipeline makes."""
    frame_id = repo.reserve_frame_id()
    image_path, thumb_path = files.save_frame_images(frame_id, scenes.exit_sign())
    repo.insert_frame(repo.NewFrame(
        id=frame_id, captured_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        image_path=image_path, thumb_path=thumb_path, width=640, height=480,
        sharpness=150.0, brightness=120.0,
    ))
    return frame_id


def on_disk(frames_dir, frame_id: int) -> bool:
    return (frames_dir / f"frames/{frame_id}.jpg").exists() or \
        (frames_dir / f"thumbs/{frame_id}.jpg").exists()


def make_old(path) -> None:
    old = time.time() - 3600
    os.utime(path, (old, old))


def test_old_frames_are_deleted_with_their_files(clean_frames, frames_dir) -> None:
    old = store(minutes_ago=settings.retention_minutes + 10)
    recent = store(minutes_ago=5)

    assert retention.purge_old_frames() == 1
    assert repo.get_frame(old) is None and not on_disk(frames_dir, old)
    assert repo.get_frame(recent) is not None
    assert (frames_dir / f"frames/{recent}.jpg").exists()
    assert (frames_dir / f"thumbs/{recent}.jpg").exists()


def test_zero_minutes_forgets_everything(clean_frames, frames_dir) -> None:
    ids = [store(minutes_ago=m) for m in (1, 2, 3)]
    assert retention.purge_old_frames(minutes=0) == 3
    assert repo.count_frames() == 0
    assert not any(on_disk(frames_dir, i) for i in ids)


def test_orphan_files_are_removed_but_fresh_ones_wait(clean_frames, frames_dir) -> None:
    kept = store(minutes_ago=1)
    for path in (frames_dir / "frames").glob("*.jpg"):
        make_old(path)  # an old file that still has its row: must stay
    orphan = frames_dir / "frames" / "999.jpg"
    orphan.write_bytes(b"jpeg")
    make_old(orphan)  # its row is gone (process killed mid-way, or deleted by hand)
    fresh = frames_dir / "thumbs" / "1000.jpg"
    fresh.write_bytes(b"jpeg")  # written just now: its row may be on its way

    assert retention.remove_orphan_files() == 1
    assert not orphan.exists() and fresh.exists()
    assert (frames_dir / f"frames/{kept}.jpg").exists()


def test_job_runs_at_start_and_survives_database_errors(clean_frames, frames_dir,
                                                        monkeypatch) -> None:
    old = store(minutes_ago=settings.retention_minutes + 1)
    job = retention.RetentionJob(interval_s=0.05)
    job.start()
    deadline = time.time() + 5
    while repo.get_frame(old) is not None and time.time() < deadline:
        time.sleep(0.05)
    assert repo.get_frame(old) is None  # cleaned as soon as the worker starts

    calls = []

    def database_down(minutes=None):
        calls.append(1)
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(retention, "run_once", database_down)
    deadline = time.time() + 5
    while len(calls) < 2 and time.time() < deadline:
        time.sleep(0.05)
    assert len(calls) >= 2  # the error was logged and the job kept going
    job.stop()
