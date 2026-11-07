"""Live snapshot: what the camera sees at the moment of the question (owner: Student B).

Stored frames are only saved when they are sharp, informative and new, so "no new
frame" can mean "same scene" or "camera covered". For questions about NOW we grab
the current frame straight from the stream (RTSP, like the ingest worker) and
judge it with the same quality measures as Student A's frame selection.
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import settings

log = logging.getLogger("uvicorn.error")

# MediaMTX serves RTSP over TCP only (B1); must be set before OpenCV opens a stream.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

TIMEOUT_MS = 3000  # give up quickly: the answer can still use stored frames
FRAMES_TO_READ = 3  # the first decoded frame after connecting can be incomplete
KEEP_SNAPSHOTS = 100  # saved for the History page; older ones are deleted

# Only reject what the model really cannot describe. Student A's storage thresholds
# (sharpness >= 60...) are stricter on purpose; a slightly soft picture is still
# readable for Gemini (tested: a clear photo of a mouse measured 57).
# Measured with a finger on the lens: brightness 5, sharpness 3, informativeness 0.
MIN_BRIGHTNESS = 25.0  # mean gray (0-255) below this: covered lens or dark room
MIN_SHARPNESS = 20.0  # Laplacian variance below this: nothing but blur
MIN_INFORMATIVE = 0.005  # edges + text below this: blank surface right against the lens


@dataclass(frozen=True)
class LiveFrame:
    jpeg: bytes
    captured_at: datetime
    usable: bool  # sharp and informative enough to describe
    reason: str  # "ok", "too_dark", "blurry" or "not_informative"
    url: str  # where the dashboard can show it ("/media/live/....jpg"), "" if not saved


def grab() -> LiveFrame | None:
    """The current camera frame, or None if the stream cannot be read now."""
    import cv2  # heavy: imported only when used

    from app.vision.quality import measure

    started = time.perf_counter()
    cap = cv2.VideoCapture(
        settings.rtsp_url,
        cv2.CAP_FFMPEG,
        [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, TIMEOUT_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, TIMEOUT_MS],
    )
    try:
        if not cap.isOpened():
            log.info("live view: stream not available")
            return None
        frame = None
        for _ in range(FRAMES_TO_READ):
            ok, image = cap.read()
            if not ok:
                break  # stream just stopped: don't wait again for the next read
            frame = image
        if frame is None:
            log.info("live view: no frame received")
            return None
    finally:
        cap.release()

    captured_at = datetime.now(UTC)
    quality = measure(frame)
    usable, reason = judge(quality.brightness, quality.sharpness, quality.informativeness)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return None
    jpeg = encoded.tobytes()
    log.info(
        "live view: %s (sharpness %.0f, brightness %.0f) in %d ms",
        reason, quality.sharpness, quality.brightness, (time.perf_counter() - started) * 1000,
    )
    return LiveFrame(jpeg, captured_at, usable, reason, _save(jpeg, captured_at))


def judge(brightness: float, sharpness: float, informativeness: float) -> tuple[bool, str]:
    """(usable, reason) for a live frame."""
    if brightness < MIN_BRIGHTNESS:
        return False, "too_dark"
    if sharpness < MIN_SHARPNESS:
        return False, "blurry"
    if informativeness < MIN_INFORMATIVE:
        return False, "not_informative"
    return True, "ok"


def _save(jpeg: bytes, captured_at: datetime) -> str:
    """Keeps the snapshot under data/frames/live/ so History can show what was seen."""
    try:
        folder = settings.frames_path / "live"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{captured_at:%Y%m%d-%H%M%S-%f}.jpg"
        (folder / name).write_bytes(jpeg)
        for old in sorted(folder.glob("*.jpg"))[:-KEEP_SNAPSHOTS]:
            old.unlink(missing_ok=True)
        return f"/media/live/{name}"  # /media serves data/frames (main.py)
    except OSError as error:
        log.warning("live view: could not save the snapshot: %s", error)
        return ""
