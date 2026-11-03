"""A3 tests: frame measurements and the keep/reject rule.

Run from backend/:  pytest tests/vision -v
"""

from datetime import UTC, datetime, timedelta

import numpy as np

from app.config import settings
from app.vision.quality import FrameSelector, dhash, hamming, measure, small_gray
from tests.vision import scenes

T0 = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


# ---------- measurements ----------

def test_sharp_frame_passes_and_blurred_frame_fails() -> None:
    sharp = measure(scenes.exit_sign()).sharpness
    mild = measure(scenes.blurred(scenes.exit_sign(), 1.5)).sharpness
    strong = measure(scenes.blurred(scenes.exit_sign(), 3)).sharpness
    assert sharp > settings.sharpness_good
    assert settings.sharpness_min <= mild < settings.sharpness_good  # A4 will sharpen these
    assert strong < settings.sharpness_min


def test_brightness_is_mean_gray() -> None:
    assert measure(np.zeros((480, 640, 3), np.uint8)).brightness == 0
    assert measure(np.full((480, 640, 3), 255, np.uint8)).brightness == 255
    assert measure(scenes.darkened(scenes.exit_sign())).brightness < settings.dark_brightness


def test_dark_but_sharp_frame_is_not_mistaken_for_blur() -> None:
    quality = measure(scenes.darkened(scenes.exit_sign()))
    assert quality.sharpness >= settings.sharpness_min
    assert quality.informativeness >= settings.informative_min


def test_dhash_similar_views_are_close_and_different_scenes_far() -> None:
    sign = dhash(small_gray(scenes.exit_sign()))
    assert 0 <= sign < 2**64
    assert hamming(sign, dhash(small_gray(scenes.jittered(scenes.exit_sign())))) < 5
    assert hamming(sign, dhash(small_gray(scenes.boxes()))) >= settings.novelty_min_bits


def test_informativeness_blank_vs_busy() -> None:
    assert measure(scenes.wall()).informativeness < settings.informative_min
    assert measure(np.zeros((480, 640, 3), np.uint8)).informativeness == 0
    assert measure(scenes.boxes()).informativeness >= settings.informative_min
    sign = measure(scenes.exit_sign())
    assert sign.informativeness >= settings.informative_min
    assert sign.text_score > 0.01  # the EXIT sign is found as text


def test_text_score_ignores_blur_and_noise() -> None:
    assert measure(scenes.blurred(scenes.exit_sign(), 6)).text_score == 0
    assert measure(scenes.wall()).text_score == 0


# ---------- keep / reject rule ----------

def test_selector_reasons() -> None:
    selector = FrameSelector()
    sign = measure(scenes.exit_sign())

    assert selector.decide(measure(scenes.blurred(scenes.exit_sign(), 3)), at(0)).reason == "blurry"
    assert selector.decide(measure(scenes.wall()), at(0)).reason == "blurry"  # flat = no edges
    noisy = measure(scenes.dark_noisy_wall())
    assert noisy.sharpness >= settings.sharpness_min  # noise alone looks "sharp"...
    assert selector.decide(noisy, at(0)).reason == "not_informative"  # ...but shows nothing

    first = selector.decide(sign, at(0))
    assert (first.keep, first.reason) == (True, "first")
    same = selector.decide(measure(scenes.jittered(scenes.exit_sign())), at(1))
    assert (same.keep, same.reason) == (False, "duplicate")
    new = selector.decide(measure(scenes.boxes()), at(2))
    assert (new.keep, new.reason) == (True, "novel")


def test_still_scene_keeps_one_frame_every_5_seconds() -> None:
    """A3 done-test: a camera pointed at the same view for 12 s at 5 fps."""
    selector = FrameSelector()
    still = measure(scenes.exit_sign())
    kept_at = [
        i / settings.ingest_fps
        for i in range(int(12 * settings.ingest_fps))
        if selector.decide(still, at(i / settings.ingest_fps)).keep
    ]
    assert kept_at == [0.0, 5.0, 10.0]


def test_blurry_frames_never_count_as_the_last_kept_frame() -> None:
    selector = FrameSelector()
    selector.decide(measure(scenes.exit_sign()), at(0))
    selector.decide(measure(scenes.blurred(scenes.boxes(), 4)), at(1))  # rejected
    # The sharp boxes frame is still new compared with the last KEPT frame (the sign)
    assert selector.decide(measure(scenes.boxes()), at(2)).reason == "novel"
