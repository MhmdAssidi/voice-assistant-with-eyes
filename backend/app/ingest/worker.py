"""Ingest worker: the "Remember" step (owner: Student A, task A2).

Run from backend/ (MediaMTX must be running, the API is optional):
    python -m app.ingest.worker                      # reads RTSP_URL from .env
    python -m app.ingest.worker --source ../eval/samples/walk.mp4

Samples the newest stream frame ~5 times per second, runs it through the
pipeline, and posts an ingest_status event every 2 s. Stop with Ctrl+C.
"""

import argparse
import logging
import threading
import time
from collections import deque

from app.config import settings
from app.ingest.grabber import FrameGrabber
from app.ingest.notifier import EventNotifier
from app.ingest.pipeline import Pipeline

log = logging.getLogger("worker")


class IngestStats:
    """Counters shown on the dashboard status bar (contract: ingest_status)."""

    def __init__(self, window: int = 50) -> None:
        self.frames_seen = 0  # frames sampled from the stream
        self.frames_kept = 0  # frames the pipeline stored
        self._durations_ms: deque[float] = deque(maxlen=window)  # last `window` frames
        self._lock = threading.Lock()

    def record(self, duration_ms: float, kept: bool) -> None:
        with self._lock:
            self.frames_seen += 1
            self.frames_kept += int(kept)
            self._durations_ms.append(duration_ms)

    @property
    def avg_process_ms(self) -> int:
        with self._lock:
            if not self._durations_ms:
                return 0
            return round(sum(self._durations_ms) / len(self._durations_ms))


class IngestWorker:
    def __init__(
        self,
        source: str,
        pipeline: Pipeline | None = None,
        notifier: EventNotifier | None = None,
    ) -> None:
        self.grabber = FrameGrabber(source, reconnect_s=settings.rtsp_reconnect_s)
        self.notifier = notifier or EventNotifier(settings.api_internal_url)
        # Loads the AI models once (OCR, YOLO, CLIP: ~30 s); the pipeline posts frame_stored
        self.pipeline = pipeline or Pipeline(notifier=self.notifier)
        self.stats = IngestStats()
        self.running = False
        self._stop = threading.Event()

    def status_data(self) -> dict:
        """Payload of the ingest_status event, exactly the keys in the contract."""
        return {
            "stream_connected": self.grabber.connected,
            "ingest_running": self.running,
            "frames_seen": self.stats.frames_seen,
            "frames_kept": self.stats.frames_kept,
            "avg_process_ms": self.stats.avg_process_ms,
        }

    def _status_loop(self) -> None:
        while not self._stop.wait(settings.status_interval_s):
            data = self.status_data()
            log.info(
                "connected=%s seen=%d kept=%d avg=%d ms",
                data["stream_connected"], data["frames_seen"],
                data["frames_kept"], data["avg_process_ms"],
            )
            self.notifier.post("ingest_status", data)

    def process_latest(self, last_seq: int) -> int:
        """Run the pipeline on the newest frame if it is new; return its seq."""
        frame = self.grabber.latest()
        if frame is None or frame.seq == last_seq:
            return last_seq
        start = time.perf_counter()
        try:
            kept = self.pipeline.process(frame)
        except Exception:  # one bad frame must never stop the live demo
            log.exception("Pipeline failed on frame %d; skipping it", frame.seq)
            kept = False
        self.stats.record((time.perf_counter() - start) * 1000, kept)
        return frame.seq

    def run(self) -> None:
        log.info("Ingest worker starting: source=%s, %.0f fps", self.grabber.source,
                 settings.ingest_fps)
        self.running = True
        self.grabber.start()
        threading.Thread(target=self._status_loop, name="status", daemon=True).start()

        period = 1.0 / settings.ingest_fps
        next_tick = time.monotonic()
        last_seq = 0
        try:
            while not self._stop.is_set():
                last_seq = self.process_latest(last_seq)
                next_tick += period
                delay = next_tick - time.monotonic()
                if delay > 0:
                    self._stop.wait(delay)
                else:  # processing was slower than 5 fps: do not try to catch up
                    next_tick = time.monotonic()
        except KeyboardInterrupt:
            log.info("Stopping (Ctrl+C)")
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        self.grabber.stop()
        self.notifier.post("ingest_status", self.status_data())  # tell the dashboard we stopped
        self.notifier.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice assistant ingest worker")
    parser.add_argument("--source", default=settings.rtsp_url,
                        help="RTSP URL or video file (default: RTSP_URL from .env)")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per event is too noisy
    IngestWorker(args.source).run()


if __name__ == "__main__":
    main()
