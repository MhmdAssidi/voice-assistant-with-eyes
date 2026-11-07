"""A9 tests: face blurring for privacy.

Fast tests check the box maths and the mosaic; the slow tests use the real YuNet
detector on two real photos shipped with ultralytics (people in a street, two
football coaches) and check that, after blurring, no face can be found any more.
Run from backend/:  pytest tests/vision/test_faces.py -v            (fast)
                    pytest tests/vision/test_faces.py -v -m slow    (real detector)
"""

import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.config import settings
from app.vision import faces
from tests.vision import scenes


def sharp_detail(image: np.ndarray) -> float:
    """Laplacian variance: high when there is fine detail (eyes, mouth...)."""
    return float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


# ---------- fast ----------

def test_expand_box_grows_and_stays_inside_the_image() -> None:
    assert faces.expand_box((100, 100, 140, 160), 640, 480) == (90, 85, 150, 175)
    assert faces.expand_box((0, 0, 40, 40), 640, 480) == (0, 0, 50, 50)  # clipped at 0
    assert faces.expand_box((620, 460, 640, 480), 640, 480) == (615, 455, 640, 480)


def test_pixelate_only_changes_the_boxes_and_destroys_detail() -> None:
    image = scenes.exit_sign()
    box = (60, 120, 340, 290)  # the sign and its caption
    result = faces.pixelate(image, [box])

    x1, y1, x2, y2 = box
    region = result[y1:y2, x1:x2]
    colours = np.unique(region.reshape(-1, 3), axis=0)
    assert len(colours) <= faces.MOSAIC_BLOCKS**2  # a mosaic of at most 6 x 6 squares
    assert sharp_detail(region) < sharp_detail(image[y1:y2, x1:x2]) / 5

    outside = np.ones(image.shape[:2], bool)
    outside[y1:y2, x1:x2] = False
    assert np.array_equal(result[outside], image[outside])  # the rest is untouched
    assert not np.array_equal(result, image) and result is not image  # input not modified


def test_pixelate_handles_tiny_and_empty_boxes() -> None:
    image = scenes.wall()
    result = faces.pixelate(image, [(10, 10, 14, 15), (50, 50, 50, 60)])  # 4x5 face, empty box
    assert result.shape == image.shape


def test_corrupted_model_download_is_rejected(tmp_path, monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def read(self) -> bytes:
            return b"not the real model"

    monkeypatch.setattr(settings, "models_dir", str(tmp_path))
    monkeypatch.setattr(faces.urllib.request, "urlopen", lambda url, timeout: FakeResponse())
    with pytest.raises(RuntimeError, match="corrupted"):
        faces.model_path()
    assert list(tmp_path.iterdir()) == []  # nothing half-written is left behind


# ---------- slow: the real detector ----------

def _asset(name: str) -> np.ndarray:
    import ultralytics

    return cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / name))


@pytest.fixture(scope="module")
def blurrer() -> faces.FaceBlurrer:
    return faces.FaceBlurrer()


@pytest.mark.slow
@pytest.mark.parametrize("photo, at_least", [("bus.jpg", 2), ("zidane.jpg", 2)])
def test_faces_are_found_and_no_longer_findable_after_blurring(blurrer, photo, at_least) -> None:
    image = _asset(photo)
    found = blurrer.find(image)
    assert len(found) >= at_least

    result = blurrer.blur(image)
    assert len(result.faces) == len(found)
    # Even a stricter detector (0.3 instead of 0.5) sees no face in any blurred area
    # (it may still fire on some random pattern elsewhere in the photo)
    strict = faces.FaceBlurrer(min_confidence=0.3)
    for x1, y1, x2, y2 in strict.find(result.image):
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        assert not any(bx1 <= cx <= bx2 and by1 <= cy <= by2
                       for bx1, by1, bx2, by2 in result.faces), "a blurred face is still findable"
    for x1, y1, x2, y2 in result.faces:
        # only flat mosaic squares are left (boxes of close faces may overlap: allow theirs too)
        colours = np.unique(result.image[y1:y2, x1:x2].reshape(-1, 3), axis=0)
        assert len(colours) <= faces.MOSAIC_BLOCKS**2 * len(result.faces)


@pytest.mark.slow
def test_scene_without_people_is_unchanged(blurrer) -> None:
    image = scenes.exit_sign()
    result = blurrer.blur(image)
    assert result.faces == [] and result.image is image


@pytest.mark.slow
def test_fast_enough(blurrer) -> None:
    frame = cv2.resize(_asset("bus.jpg"), (640, 480))
    blurrer.blur(frame)  # warm up
    start = time.perf_counter()
    for _ in range(3):
        blurrer.blur(frame)
    assert (time.perf_counter() - start) / 3 < 0.3  # ~70 ms measured; OCR takes ~2 s
