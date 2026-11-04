"""Sign photos for OCR tests, drawn with Pillow (owner: Student A).

Arabic letters change shape depending on their neighbours and are written right
to left. arabic_reshaper picks the joined letter forms and bidi puts them in
display order, so the drawn sign looks like a real printed one (Pillow alone
cannot do this on Windows, and OpenCV's putText has no Arabic at all).
Windows fonts are used when present, otherwise DejaVu (Linux).
"""

from pathlib import Path

import arabic_reshaper
import cv2
import numpy as np
from bidi import get_display
from PIL import Image, ImageDraw, ImageFont

from app.vision.ocr import is_arabic

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def sign(lines: list[str], background=(30, 120, 40), color=(255, 255, 255),
         size: int = 64) -> np.ndarray:
    """A 640x480 photo of a wall with a coloured sign carrying `lines` of text (BGR)."""
    image = Image.new("RGB", (640, 480), (170, 168, 160))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 90, 600, 390), radius=18, fill=background)
    font = _font(size)
    y = 240 - (len(lines) * (size + 24)) // 2
    for line in lines:
        if is_arabic(line):
            line = get_display(arabic_reshaper.reshape(line))
        width = draw.textlength(line, font=font)
        draw.text(((640 - width) / 2, y), line, font=font, fill=color)
        y += size + 24
    noisy = np.asarray(image, dtype=np.float64)
    noisy += np.random.default_rng(1).normal(0, 3, noisy.shape)  # camera sensor noise
    return cv2.cvtColor(np.clip(noisy, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)


def english() -> np.ndarray:
    return sign(["EXIT", "Room 204"])


def french() -> np.ndarray:
    return sign(["Sortie", "Escalier"], background=(20, 60, 140))


def arabic() -> np.ndarray:
    return sign(["مخرج", "الطابق الأول"], background=(140, 30, 30))
