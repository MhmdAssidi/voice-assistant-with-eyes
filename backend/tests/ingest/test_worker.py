"""A2 tests: frame grabber, event notifier and worker loop (no stream or API needed).

Run from backend/:  pytest tests/ingest -v
"""

import json
import time
from datetime import UTC, datetime

import cv2
import httpx
import numpy as np

from app.ingest.grabber import FrameGrabber, GrabbedFrame
from app.ingest.notifier import EventNotifier
from app.ingest.worker import IngestStats, IngestWorker


def _wait_for(condition, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def _make_video(path, frames: int = 30) -> str:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 15, (64, 48))
    for i in range(frames):
        writer.write(np.full((48, 64, 3), i * 8, dtype=np.uint8))
    writer.release()
    return str(path)


def test_grabber_reads_a_video_file(tmp_path) -> None:
    grabber = FrameGrabber(_make_video(tmp_path / "clip.avi"), reconnect_s=0.1)
    grabber.start()
    try:
        assert _wait_for(lambda: grabber.latest() is not None and grabber.latest().seq >= 3)
        frame = grabber.latest()
        assert frame.image.shape == (48, 64, 3)
        assert frame.captured_at.tzinfo is not None
    finally:
        grabber.stop()


def test_grabber_keeps_retrying_an_unreachable_stream() -> None:
    grabber = FrameGrabber("rtsp://127.0.0.1:1/live", reconnect_s=0.1)
    grabber.start()
    time.sleep(0.5)
    assert grabber.connected is False
    assert grabber.latest() is None
    grabber.stop()


def test_notifier_never_raises_when_api_is_down() -> None:
    notifier = EventNotifier("http://127.0.0.1:1", timeout_s=0.5)
    assert notifier.post("ingest_status", {"frames_seen": 1}) is False
    assert notifier.post("ingest_status", {"frames_seen": 2}) is False  # still no exception


def test_notifier_sends_a_contract_event() -> None:
    received = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True})

    notifier = EventNotifier("http://api")
    notifier._client = httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))
    assert notifier.post("ingest_status", {"frames_seen": 5}) is True

    path, body = received[0]
    assert path == "/api/internal/events"
    assert body["type"] == "ingest_status"
    assert body["data"] == {"frames_seen": 5}
    datetime.fromisoformat(body["ts"])


def test_stats_rolling_average() -> None:
    stats = IngestStats(window=2)
    assert stats.avg_process_ms == 0
    for ms, kept in [(100, False), (20, True), (40, False)]:
        stats.record(ms, kept)
    assert stats.frames_seen == 3
    assert stats.frames_kept == 1
    assert stats.avg_process_ms == 30  # only the last 2 frames


class _FakeGrabber:
    source = "fake"
    connected = True

    def __init__(self) -> None:
        self.frame: GrabbedFrame | None = None

    def latest(self) -> GrabbedFrame | None:
        return self.frame


class _FailingPipeline:
    def process(self, frame: GrabbedFrame) -> bool:
        raise RuntimeError("broken frame")


def test_worker_processes_each_frame_once_and_survives_errors() -> None:
    worker = IngestWorker("fake", pipeline=_FailingPipeline(), notifier=EventNotifier("http://x"))
    worker.grabber = _FakeGrabber()

    assert worker.process_latest(0) == 0  # no frame yet

    worker.grabber.frame = GrabbedFrame(1, datetime.now(UTC), np.zeros((4, 4, 3), np.uint8))
    last = worker.process_latest(0)  # the pipeline raises, the worker must not
    assert last == 1
    assert worker.process_latest(last) == 1  # same frame is not processed twice
    assert worker.stats.frames_seen == 1
    assert worker.stats.frames_kept == 0

    assert set(worker.status_data()) == {
        "stream_connected", "ingest_running", "frames_seen", "frames_kept", "avg_process_ms",
    }
