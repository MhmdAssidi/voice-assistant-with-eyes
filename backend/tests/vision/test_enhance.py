"""A4 tests: low-light enhancement.

Fast tests check the maths (gamma, colours, contrast, speed) on synthetic scenes;
the slow test shows the real benefit: EasyOCR cannot read a very dark sign until
it is enhanced.
Run from backend/:  pytest tests/vision/test_enhance.py -v            (fast)
                    pytest tests/vision/test_enhance.py -v -m slow    (real OCR)
"""

import time

import cv2
import numpy as np
import pytest

from app.config import settings
from app.vision import enhance as E
from app.vision.quality import measure
from tests.vision import scenes, signs


def night(image: np.ndarray, factor: float, noise: float = 6.0) -> np.ndarray:
    """The same view in low light: much less signal, the same sensor noise."""
    rng = np.random.default_rng(2)
    dark = image.astype(np.float64) * factor + rng.normal(0, noise, image.shape)
    return np.clip(np.round(dark), 0, 255).astype(np.uint8)


def gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


# ---------- the maths ----------

def test_gamma_lifts_dark_frames_and_never_darkens() -> None:
    assert E.choose_gamma(E.TARGET_MEAN) == pytest.approx(1.0)
    assert E.choose_gamma(200) == 1.0  # bright frame: never darkened
    assert E.choose_gamma(40) < 0.7  # dark frame: lifted
    assert E.choose_gamma(2) == E.GAMMA_RANGE[0]  # almost black: the strongest lift, no more


def test_gamma_lut_keeps_black_and_white() -> None:
    lut = E.gamma_lut(0.5)
    assert (lut[0], lut[255]) == (0, 255)
    assert np.all(np.diff(lut.astype(int)) >= 0)  # keeps the order of gray levels
    assert lut[64] > 64  # a dark gray becomes lighter


# ---------- the enhancement ----------

def test_bright_frame_is_left_alone() -> None:
    image = scenes.exit_sign()
    result = E.enhance(image, measure(image).brightness)
    assert result.enhanced is False
    assert result.image is image


def test_dark_frame_is_brightened_with_more_contrast() -> None:
    dark = night(scenes.exit_sign(), 0.12)
    brightness = measure(dark).brightness
    assert brightness < settings.dark_brightness

    result = E.enhance(dark, brightness)
    assert result.enhanced is True
    assert result.image.shape == dark.shape and result.image.dtype == np.uint8
    assert gray(result.image).mean() > 3 * gray(dark).mean()
    assert gray(result.image).std() > 3 * gray(dark).std()  # contrast stretched


def test_colours_are_kept() -> None:
    """Only the lightness changes: the green sign is still green.

    (In near-black frames there is almost no colour left to recover: that is physics.)
    """
    dark = night(scenes.exit_sign(), 0.3)
    result = E.enhance(dark, measure(dark).brightness).image
    blue, green, red = cv2.split(result[130:150, 70:90].astype(float))  # inside the green sign
    assert green.mean() > red.mean() + 25 and green.mean() > blue.mean() + 25


def test_noise_is_not_blown_up() -> None:
    """Denoising before CLAHE: a dark plain wall ends up smoother than with gamma alone."""
    wall = scenes.dark_noisy_wall()
    result = E.enhance(wall, measure(wall).brightness).image
    lifted_only = cv2.LUT(gray(wall), E.gamma_lut(E.choose_gamma(gray(wall).mean())))
    assert gray(result).std() < lifted_only.std()


def test_fast_enough_for_live_video() -> None:
    dark = night(signs.english(), 0.08)
    E.enhance(dark, 10)  # warm up OpenCV
    start = time.perf_counter()
    for _ in range(5):
        E.enhance(dark, 10)
    assert (time.perf_counter() - start) / 5 < 0.05  # < 50 ms per frame (OCR takes ~2 s)


# ---------- slow: the real benefit for OCR ----------

@pytest.mark.slow
@pytest.mark.parametrize("make_sign, words", [
    (signs.english, ["exit", "room"]),
    (signs.french, ["sortie", "escalier"]),
])
def test_very_dark_sign_is_only_readable_after_enhancement(make_sign, words) -> None:
    from app.vision.ocr import OcrEngine

    engine = OcrEngine()
    dark = night(make_sign(), 0.06)  # mean brightness ~7 / 255
    assert words[0] not in engine.read(dark).text.lower()  # too dark to read as it is

    enhanced = E.enhance(dark, measure(dark).brightness)
    assert enhanced.enhanced
    text = enhanced and engine.read(enhanced.image).text.lower()
    assert all(word in text for word in words), text
