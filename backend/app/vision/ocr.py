"""OCR: read signs and labels in English, French and Arabic (owner: Student A, task A5).

EasyOCR works in two stages: a DETECTOR (CRAFT) finds where text is, then a
RECOGNIZER reads the letters inside each box. There is one recognizer per script,
so we load two readers ONCE at worker start (about 15 s):
    ['en', 'fr']  Latin script: English and French (accents included)
    ['ar', 'en']  Arabic script
Measured on this laptop's CPU, the detector is the slow part (~3.3 s at 640 px),
so per frame we:
  1. detect text boxes ONCE, on a copy ocr_detect_width wide (~2x faster),
  2. read every box with the Latin recognizer on the full-size frame (~0.2 s),
  3. re-read with the Arabic recognizer only the boxes the Latin one is unsure
     about (< ocr_latin_sure). Latin reads Arabic letters as nonsense with
     confidence ~0.1-0.2, so Arabic text always gets its second reading, and
     signs in English or French skip the slower Arabic model (~1.4 s).

If even the best block is unsure (< ocr_retry_below), we read again on a gray,
adaptive-threshold copy: black text on white, which helps with glare, uneven light
and coloured signs.

Try it on your own photos:
    python -m app.vision.ocr sign.jpg
"""

import logging
import re
import sys
import time
from dataclasses import dataclass

import cv2
import numpy as np

from app.config import settings
from app.contracts import OcrBlock

log = logging.getLogger(__name__)

READER_LANGUAGES = (["en", "fr"], ["ar", "en"])
SAME_TEXT_IOU = 0.5  # boxes overlapping this much are the same text read twice
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


@dataclass
class OcrResult:
    text: str  # all blocks, top-to-bottom, one line of the sign per line
    blocks: list[OcrBlock]


# ---------- pure helpers (no model needed, unit-tested) ----------

def iou(a: list[int], b: list[int]) -> float:
    """Intersection over union of two [x1, y1, x2, y2] boxes."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def is_arabic(text: str) -> bool:
    return bool(_ARABIC.search(text))


def to_block(raw: tuple) -> OcrBlock:
    """EasyOCR result (4 corner points, text, confidence) -> contract OcrBlock."""
    points, text, confidence = raw
    xs = [int(p[0]) for p in points]
    ys = [int(p[1]) for p in points]
    return OcrBlock(
        text=text.strip(), confidence=round(float(confidence), 3),
        bbox=[min(xs), min(ys), max(xs), max(ys)],
    )


def merge_blocks(blocks: list[OcrBlock], min_confidence: float) -> list[OcrBlock]:
    """Drop unsure and empty blocks; where two readers found the same text keep the surer one."""
    kept: list[OcrBlock] = []
    for block in sorted(blocks, key=lambda b: b.confidence, reverse=True):
        if block.confidence < min_confidence or not block.text:
            continue
        if all(iou(block.bbox, other.bbox) < SAME_TEXT_IOU for other in kept):
            kept.append(block)
    return kept


def reading_order(blocks: list[OcrBlock]) -> list[list[OcrBlock]]:
    """Group blocks into lines (top to bottom); order words inside a line.

    Two blocks share a line when their vertical centres are closer than half the
    smaller height. Latin lines read left to right, Arabic lines right to left.
    """
    lines: list[list[OcrBlock]] = []
    for block in sorted(blocks, key=lambda b: (b.bbox[1] + b.bbox[3]) / 2):
        centre = (block.bbox[1] + block.bbox[3]) / 2
        height = block.bbox[3] - block.bbox[1]
        if lines:
            last = lines[-1][-1]
            last_centre = (last.bbox[1] + last.bbox[3]) / 2
            if abs(centre - last_centre) < min(height, last.bbox[3] - last.bbox[1]) / 2:
                lines[-1].append(block)
                continue
        lines.append([block])
    for line in lines:
        arabic = sum(is_arabic(b.text) for b in line) > len(line) / 2
        line.sort(key=lambda b: b.bbox[0], reverse=arabic)
    return lines


def to_result(blocks: list[OcrBlock]) -> OcrResult:
    lines = reading_order(blocks)
    text = "\n".join(" ".join(b.text for b in line) for line in lines)
    return OcrResult(text=text, blocks=[b for line in lines for b in line])


def thresholded(image: np.ndarray) -> np.ndarray:
    """Gray + adaptive threshold: dark text on a white background, even under uneven light."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    if np.mean(binary) < 127:  # mostly black: light text on a dark sign, flip it
        binary = cv2.bitwise_not(binary)
    return binary


# ---------- the engine (loads EasyOCR) ----------

class OcrEngine:
    def __init__(self) -> None:
        import easyocr  # heavy import (PyTorch); only when OCR is really used

        model_dir = settings.models_path / "easyocr"
        model_dir.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        self.latin, self.arabic = (
            easyocr.Reader(
                languages, gpu=False, model_storage_directory=str(model_dir),
                user_network_directory=str(model_dir), verbose=False,
            )
            for languages in READER_LANGUAGES
        )
        self._read_all(np.full((240, 320, 3), 128, np.uint8))  # warm up: first call is slow
        log.info("OCR readers %s loaded in %.1f s", READER_LANGUAGES,
                 time.perf_counter() - start)

    def _detect(self, image: np.ndarray) -> tuple[list, list]:
        """Text boxes in full-frame pixels, found on a smaller copy."""
        scale = min(1.0, settings.ocr_detect_width / image.shape[1])
        small = image if scale == 1.0 else cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
        )
        horizontal, free = self.latin.detect(small)
        # horizontal boxes are [x_min, x_max, y_min, y_max]; free boxes are 4 (x, y) corners
        horizontal = [[round(v / scale) for v in box] for box in horizontal[0]]
        free = [[[round(x / scale), round(y / scale)] for x, y in box] for box in free[0]]
        return horizontal, free

    def _read_all(self, image: np.ndarray) -> list[OcrBlock]:
        horizontal, free = self._detect(image)
        if not horizontal and not free:
            return []
        blocks = [to_block(raw) for raw in self.latin.recognize(image, horizontal, free)]
        unsure = [b for b in blocks if b.confidence < settings.ocr_latin_sure]
        if unsure:
            boxes = [[b.bbox[0], b.bbox[2], b.bbox[1], b.bbox[3]] for b in unsure]
            blocks += [to_block(raw) for raw in self.arabic.recognize(image, boxes, [])]
        return blocks  # merge_blocks keeps the surer reading of each box

    def read(self, image: np.ndarray) -> OcrResult:
        """Text on one BGR frame. Empty text and no blocks when nothing is readable."""
        raw = self._read_all(image)
        best = max((b.confidence for b in raw), default=0.0)
        if best < settings.ocr_retry_below:
            raw += self._read_all(thresholded(image))
        return to_result(merge_blocks(raw, settings.ocr_min_confidence))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = OcrEngine()
    for path in sys.argv[1:]:
        frame = cv2.imread(path)
        if frame is None:
            print(f"{path}: cannot read")
            continue
        t0 = time.perf_counter()
        result = engine.read(frame)
        print(f"--- {path} ({(time.perf_counter() - t0) * 1000:.0f} ms)")
        for block in result.blocks:
            print(f"  {block.confidence:.2f}  {block.bbox}  {block.text}")
        print("  text:", result.text.replace("\n", " | ") or "(none)")
