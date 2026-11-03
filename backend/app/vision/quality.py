"""Frame selection: keep only sharp, new and informative frames (owner: Student A, task A3).

Every sampled frame (5 per second) is measured on a small gray copy, which is fast
and makes the numbers independent of the camera resolution:
- sharpness:  variance of the Laplacian. Edges give big second derivatives; blur
              flattens them, so a blurry frame has a low variance.
- brightness: mean gray level, 0 (black) .. 255 (white). Used by A4 for dark frames.
- dhash:      64-bit "difference hash": shrink to 9x8 pixels and record, for each
              pixel, whether its right neighbour is brighter. Similar images give
              similar bits, so the Hamming distance between two hashes = how different.
- informativeness: edge density (share of edge pixels) + text score (share of the
              image covered by text-like regions). A blank wall scores ~0.

Rule: keep if sharp enough AND (new enough OR keep_every_s since the last kept frame)
AND informative enough.

Try it on your own images or videos (prints the measurements):
    python -m app.vision.quality photo.jpg ../eval/samples/walk.mp4
"""

import sys
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np

from app.config import settings

ANALYSIS_WIDTH = 320
MIN_STROKE_CONTRAST = 40  # gray levels between a letter stroke and its background


@dataclass
class FrameQuality:
    sharpness: float
    brightness: float
    dhash: int  # unsigned 64-bit
    edge_density: float  # 0..1
    text_score: float  # 0..1

    @property
    def informativeness(self) -> float:
        return self.edge_density + self.text_score


@dataclass
class Decision:
    keep: bool
    # kept: "first" | "novel" | "periodic";  rejected: "blurry" | "not_informative" | "duplicate"
    reason: str


def small_gray(image: np.ndarray, width: int = ANALYSIS_WIDTH) -> np.ndarray:
    """Gray copy resized to `width` pixels wide (aspect ratio kept)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height = max(1, round(gray.shape[0] * width / gray.shape[1]))
    return cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)


def sharpness(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def dhash(gray: np.ndarray) -> int:
    tiny = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (tiny[:, 1:] > tiny[:, :-1]).flatten()  # 8 rows x 8 comparisons = 64 bits
    return int(sum(1 << i for i, bit in enumerate(bits) if bit))


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def edge_density(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 100, 200)
    return float(np.count_nonzero(edges)) / edges.size


def text_score(gray: np.ndarray) -> float:
    """Share of the image covered by regions shaped like lines of text.

    Morphological gradient (dilate - erode) lights up letter strokes; closing with a
    wide, flat kernel joins the letters of a word into one blob; blobs that are
    wider than tall, not too big and densely filled are counted as text.
    """
    gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    otsu, _ = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    # Otsu always splits the image in two, even a blurry one; real strokes need contrast
    _, binary = cv2.threshold(gradient, max(otsu, MIN_STROKE_CONTRAST), 255, cv2.THRESH_BINARY)
    if np.count_nonzero(binary) == 0:
        return 0.0
    joined = cv2.morphologyEx(
        binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1))
    )
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height = gray.shape[0]
    text_area = 0
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 8 or h < 5 or h > height // 4 or w < 1.5 * h:
            continue  # too small, too tall or not wide enough to be a word
        fill = np.count_nonzero(joined[y : y + h, x : x + w]) / (w * h)
        if fill >= 0.45:
            text_area += w * h
    return min(1.0, text_area / gray.size)


def measure(image: np.ndarray) -> FrameQuality:
    """All measurements for one BGR frame (a few milliseconds on a laptop CPU)."""
    gray = small_gray(image)
    brightness = float(gray.mean())
    if brightness < settings.dark_brightness:
        # Low light also means low contrast, which would make a sharp dark frame look
        # blurry and empty. Measure a contrast-stretched copy so A4 can brighten it later.
        gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    return FrameQuality(
        sharpness=sharpness(gray),
        brightness=brightness,
        dhash=dhash(gray),
        edge_density=edge_density(gray),
        text_score=text_score(gray),
    )


class FrameSelector:
    """Remembers the last kept frame and decides whether a new one is worth keeping."""

    def __init__(
        self,
        sharpness_min: float = settings.sharpness_min,
        novelty_min_bits: int = settings.novelty_min_bits,
        keep_every_s: float = settings.keep_every_s,
        informative_min: float = settings.informative_min,
    ) -> None:
        self.sharpness_min = sharpness_min
        self.novelty_min_bits = novelty_min_bits
        self.keep_every_s = keep_every_s
        self.informative_min = informative_min
        self.last_hash: int | None = None
        self.last_kept_at: datetime | None = None

    def decide(self, quality: FrameQuality, captured_at: datetime) -> Decision:
        if quality.sharpness < self.sharpness_min:
            return Decision(False, "blurry")
        if quality.informativeness < self.informative_min:
            return Decision(False, "not_informative")

        if self.last_hash is None or self.last_kept_at is None:
            reason = "first"
        elif hamming(quality.dhash, self.last_hash) >= self.novelty_min_bits:
            reason = "novel"
        elif (captured_at - self.last_kept_at).total_seconds() >= self.keep_every_s:
            reason = "periodic"  # same view, but keep the memory fresh
        else:
            return Decision(False, "duplicate")

        self.last_hash = quality.dhash
        self.last_kept_at = captured_at
        return Decision(True, reason)


def _print_measurements(path: str) -> None:
    image = cv2.imread(path)
    frames = [image] if image is not None else []
    if not frames:  # not an image: read a video, one frame per second
        cap = cv2.VideoCapture(path)
        step = max(1, round(cap.get(cv2.CAP_PROP_FPS) or 15))
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                frames.append(frame)
            index += 1
        cap.release()
    if not frames:
        print(f"{path}: cannot read")
        return
    for i, frame in enumerate(frames):
        q = measure(frame)
        print(
            f"{path} [{i}]: sharpness={q.sharpness:.0f} brightness={q.brightness:.0f} "
            f"edges={q.edge_density:.3f} text={q.text_score:.3f} "
            f"informative={q.informativeness:.3f} dhash={q.dhash:016x}"
        )


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        _print_measurements(arg)
