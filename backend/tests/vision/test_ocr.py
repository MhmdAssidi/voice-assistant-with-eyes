"""A5 tests: OCR merging and reading order (fast) and real EasyOCR reading (slow).

Run from backend/:
    pytest tests/vision/test_ocr.py -v            # fast tests only (CI)
    pytest tests/vision/test_ocr.py -v -m slow    # also reads the en/fr/ar signs
"""

import numpy as np
import pytest

from app.contracts import OcrBlock
from app.vision.ocr import (
    iou,
    is_arabic,
    merge_blocks,
    thresholded,
    to_block,
    to_result,
)


def block(text: str, confidence: float, bbox: list[int]) -> OcrBlock:
    return OcrBlock(text=text, confidence=confidence, bbox=bbox)


# ---------- fast: pure logic ----------

def test_iou() -> None:
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    assert iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)


def test_to_block_converts_corner_points() -> None:
    raw = ([[10, 20], [110, 22], [111, 60], [9, 58]], " EXIT ", np.float64(0.93456))
    assert to_block(raw) == OcrBlock(text="EXIT", confidence=0.935, bbox=[9, 20, 111, 60])


def test_merge_drops_unsure_and_keeps_the_surer_duplicate() -> None:
    blocks = [
        block("EXIT", 0.95, [100, 100, 300, 160]),  # read by the en/fr reader
        block("EXlT", 0.55, [102, 101, 298, 161]),  # same place, read by the ar/en reader
        block("noise", 0.2, [400, 400, 420, 410]),  # below 0.4
        block("", 0.9, [0, 0, 5, 5]),  # empty
        block("204", 0.8, [100, 200, 180, 240]),
    ]
    kept = merge_blocks(blocks, min_confidence=0.4)
    assert [b.text for b in kept] == ["EXIT", "204"]


def test_reading_order_top_to_bottom_left_to_right() -> None:
    result = to_result([
        block("204", 0.9, [260, 200, 330, 240]),
        block("EXIT", 0.9, [200, 100, 400, 160]),
        block("Room", 0.9, [120, 202, 240, 238]),
    ])
    assert result.text == "EXIT\nRoom 204"
    assert [b.text for b in result.blocks] == ["EXIT", "Room", "204"]


def test_arabic_line_reads_right_to_left() -> None:
    # "الطابق" (the floor) is on the right, "الأول" (first) on the left
    result = to_result([
        block("الأول", 0.9, [150, 100, 280, 150]),
        block("الطابق", 0.9, [300, 100, 470, 150]),
    ])
    assert result.text == "الطابق الأول"
    assert is_arabic("مخرج") and not is_arabic("Sortie")


def test_no_text_gives_empty_result() -> None:
    result = to_result([])
    assert result.text == "" and result.blocks == []


def test_thresholded_is_dark_text_on_white() -> None:
    light_on_dark = np.zeros((100, 200, 3), np.uint8)
    light_on_dark[40:60, 50:150] = 255  # a white bar (light "text") on black
    binary = thresholded(light_on_dark)
    assert binary.ndim == 2
    assert binary.mean() > 127  # background became white


# ---------- slow: real EasyOCR on drawn signs ----------

@pytest.fixture(scope="module")
def engine():
    from app.vision.ocr import OcrEngine

    return OcrEngine()


def _words(text: str) -> str:
    return text.lower().replace("\n", " ")


@pytest.mark.slow
def test_reads_english_sign(engine) -> None:
    from tests.vision import signs

    text = _words(engine.read(signs.english()).text)
    assert "exit" in text
    assert "204" in text


@pytest.mark.slow
def test_reads_french_sign(engine) -> None:
    from tests.vision import signs

    text = _words(engine.read(signs.french()).text)
    assert "sortie" in text
    assert "escalier" in text


@pytest.mark.slow
def test_reads_arabic_sign(engine) -> None:
    from tests.vision import signs

    result = engine.read(signs.arabic())
    assert "مخرج" in result.text  # "exit"
    assert any(is_arabic(b.text) for b in result.blocks)


@pytest.mark.slow
def test_blank_wall_has_no_text(engine) -> None:
    from tests.vision import scenes

    result = engine.read(scenes.wall())
    assert result.text == ""
