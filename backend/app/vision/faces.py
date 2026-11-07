"""Face blurring for privacy (owner: Student A, task A9).

Every kept frame has its faces pixelated BEFORE it is stored, so no face of a passer-by
ever reaches the disk, the dashboard or the cloud vision model (Gemini). This is face
DETECTION only ("there is a face here"), never face recognition ("this is Ali"): no
identity, no face embedding, nothing about the face is kept.

Detector: YuNet, a tiny (230 KB) CNN from the official OpenCV model zoo, run with
OpenCV's built-in cv2.FaceDetectorYN (~70 ms per 640x480 frame on a laptop CPU).
The weights download once to MODELS_DIR (checked with SHA-256).

For privacy a missed face is worse than blurring something that is not a face, so
the score threshold is low (FACE_MIN_CONFIDENCE = 0.5) and every box is enlarged by
25% to cover hair and ears. Pixelation (a coarse mosaic) is used rather than a light
blur: the original pixels cannot be recovered from it. The mosaic is 6 x 6 squares:
measured on real photos, an 8 x 8 mosaic still looked like a face to the detector
(score 0.6), while after 6 x 6 nothing face-like is found even at a 0.3 threshold.

Try it on your own photos (writes <name>_blurred.jpg next to each):
    python -m app.vision.faces photo.jpg
"""

import hashlib
import logging
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from app.config import settings

log = logging.getLogger(__name__)

MODEL_FILE = "face_detection_yunet_2023mar.onnx"
MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/" + MODEL_FILE
)
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

EXPAND = 0.25  # enlarge each face box by 25% on every side
MOSAIC_BLOCKS = 6  # a face becomes at most 6 x 6 coloured squares
NMS_THRESHOLD = 0.3  # overlapping boxes of the same face are merged
MAX_FACES = 5000  # YuNet keeps this many candidates before the score threshold

Box = tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels


@dataclass
class Blurred:
    image: np.ndarray  # BGR, faces pixelated (the input itself when there is no face)
    faces: list[Box] = field(default_factory=list)  # the enlarged boxes that were blurred


def expand_box(box: Box, width: int, height: int, ratio: float = EXPAND) -> Box:
    """Grow a box by `ratio` of its size on every side, clipped to the image."""
    x1, y1, x2, y2 = box
    dx, dy = round((x2 - x1) * ratio), round((y2 - y1) * ratio)
    return max(0, x1 - dx), max(0, y1 - dy), min(width, x2 + dx), min(height, y2 + dy)


def pixelate(image: np.ndarray, boxes: list[Box]) -> np.ndarray:
    """Copy of the image with each box replaced by a coarse mosaic (irreversible)."""
    result = image.copy()
    for x1, y1, x2, y2 in boxes:
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue
        region = result[y1:y2, x1:x2]
        small = cv2.resize(region, (min(MOSAIC_BLOCKS, w), min(MOSAIC_BLOCKS, h)),
                           interpolation=cv2.INTER_AREA)  # average colour of each square
        result[y1:y2, x1:x2] = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_path() -> Path:
    """The YuNet weights, downloaded once (and checked) into MODELS_DIR."""
    path = settings.models_path / MODEL_FILE
    if path.is_file() and _sha256(path) == MODEL_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading the face detector (230 KB) to %s", path)
    partial = path.with_suffix(".part")
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
        partial.write_bytes(response.read())
    if _sha256(partial) != MODEL_SHA256:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Face detector download from {MODEL_URL} is corrupted")
    partial.replace(path)
    return path


class FaceBlurrer:
    def __init__(self, min_confidence: float | None = None) -> None:
        threshold = settings.face_min_confidence if min_confidence is None else min_confidence
        self.detector = cv2.FaceDetectorYN.create(
            str(model_path()), "", (320, 320), threshold, NMS_THRESHOLD, MAX_FACES
        )

    def find(self, image: np.ndarray) -> list[Box]:
        """Face boxes (x1, y1, x2, y2), NOT enlarged."""
        height, width = image.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(image)
        if faces is None:
            return []
        boxes = []
        for face in faces:  # x, y, w, h, 5 landmarks (10 numbers), score
            x, y, w, h = (round(float(v)) for v in face[:4])
            boxes.append((max(0, x), max(0, y), min(width, x + w), min(height, y + h)))
        return boxes

    def blur(self, image: np.ndarray) -> Blurred:
        """Pixelate every face (enlarged by EXPAND) in a copy of the image."""
        height, width = image.shape[:2]
        boxes = [expand_box(box, width, height) for box in self.find(image)]
        if not boxes:
            return Blurred(image)
        return Blurred(pixelate(image, boxes), boxes)


def _blur_files(paths: list[str]) -> None:
    blurrer = FaceBlurrer()
    for path in paths:
        image = cv2.imread(path)
        if image is None:
            print(f"{path}: cannot read")
            continue
        result = blurrer.blur(image)
        out = Path(path).with_name(f"{Path(path).stem}_blurred.jpg")
        cv2.imwrite(str(out), result.image)
        print(f"{path}: {len(result.faces)} face(s) blurred, saved {out}")


if __name__ == "__main__":
    _blur_files(sys.argv[1:])
