"""RTSP frame grabber (owner: Student A, task A2).

A background thread reads the stream as fast as it arrives and keeps only the
NEWEST frame. The worker samples that frame ~5 times per second. Reading
continuously matters: if we read slower than the stream's 15 fps, OpenCV's
buffer fills up and we would analyse video from several seconds ago.

When the stream drops (phone locked, Wi-Fi glitch) the thread releases the
capture and tries again every `reconnect_s` seconds, forever.

The source can also be a video file (e.g. eval/samples/walk.mp4): it is played
at its real speed and starts again from the beginning when it ends.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

# MediaMTX serves RTSP over TCP only (see infra/mediamtx/mediamtx.yml).
# Must be set before OpenCV opens its first stream.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402  (must come after the environment variable above)

log = logging.getLogger(__name__)

OPEN_TIMEOUT_MS = 5000  # give up opening a stream that does not answer
READ_TIMEOUT_MS = 5000  # treat 5 s without a frame as a dropped stream


@dataclass
class GrabbedFrame:
    seq: int  # increases by 1 for every frame received; tells new frames apart
    captured_at: datetime  # UTC time the frame arrived
    image: np.ndarray  # BGR image, as OpenCV gives it


def _is_live(source: str) -> bool:
    return source.lower().startswith(("rtsp://", "rtsps://", "http://", "https://"))


class FrameGrabber:
    def __init__(self, source: str, reconnect_s: float = 2.0) -> None:
        self.source = source
        self.reconnect_s = reconnect_s
        self.connected = False
        self._latest: GrabbedFrame | None = None
        self._seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="frame-grabber", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def latest(self) -> GrabbedFrame | None:
        """The newest frame received so far (None before the first one)."""
        with self._lock:
            return self._latest

    def _open(self) -> cv2.VideoCapture | None:
        params = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS,
        ]
        cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, params)
        if cap.isOpened():
            return cap
        cap.release()
        return None

    def _run(self) -> None:
        live = _is_live(self.source)
        while not self._stop.is_set():
            cap = self._open()
            if cap is None:
                log.warning("Cannot open %s; retrying in %.0f s", self.source, self.reconnect_s)
                self._stop.wait(self.reconnect_s)
                continue

            # A file has no real-time clock, so we pace it at its own frame rate
            file_delay = 0.0 if live else 1.0 / (cap.get(cv2.CAP_PROP_FPS) or 15.0)
            self.connected = True
            log.info("Stream connected: %s", self.source)

            while not self._stop.is_set():
                ok, image = cap.read()
                if not ok or image is None:
                    break
                with self._lock:
                    self._seq += 1
                    self._latest = GrabbedFrame(self._seq, datetime.now(UTC), image)
                if file_delay:
                    time.sleep(file_delay)

            cap.release()
            self.connected = False
            if not self._stop.is_set():
                log.warning("Stream lost; reconnecting in %.0f s", self.reconnect_s)
                self._stop.wait(self.reconnect_s)
