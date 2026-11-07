"""A11 tests: warnings for stairs and closed doors (CLIP zero-shot).

Fast tests use hand-made vectors (no model); the slow tests use the real CLIP model
on real photos from Wikimedia Commons (freely licensed, downloaded once into
data/test_images, not committed) and on everyday scenes that must NOT warn.
Run from backend/:  pytest tests/vision/test_hazards.py -v            (fast)
                    pytest tests/vision/test_hazards.py -v -m slow    (real CLIP)
"""

import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.config import settings
from app.vision import hazards
from tests.vision import scenes, signs

T0 = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)


class FakeEmbedder:
    """Prompt i gets the unit vector e_i, so a frame can 'look like' any prompt."""

    def embed_prompts(self, texts: list[str]) -> np.ndarray:
        return np.eye(len(texts), 512, dtype=np.float32)


def looks_like(kind: str, strength: float = 0.3) -> np.ndarray:
    """An image vector close to the first prompt of `kind`."""
    sentences = [p for prompts in hazards.PROMPTS.values() for p in prompts]
    index = sentences.index(hazards.PROMPTS[kind][0])
    vector = np.zeros(512, np.float32)
    vector[index] = strength
    vector[511] = np.sqrt(1 - strength**2)
    return vector


@pytest.fixture
def detector() -> hazards.HazardDetector:
    return hazards.HazardDetector(FakeEmbedder(), cooldown_s=15)


# ---------- fast ----------

def test_probabilities_sum_to_one(detector) -> None:
    probabilities = detector.probabilities(looks_like("stairs"))
    assert set(probabilities) == {"closed_door", "stairs", "other"}
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert probabilities["stairs"] > 0.9


def test_stairs_warn_with_the_contract_payload(detector) -> None:
    [hazard] = detector.check(looks_like("stairs"), T0)
    assert hazard.kind == "stairs"
    assert hazard.event_data(42) == {
        "kind": "stairs", "confidence": round(hazard.confidence, 3), "frame_id": 42,
        "position": "center",
    }


def test_everyday_scene_does_not_warn(detector) -> None:
    assert detector.check(looks_like("other"), T0) == []


def test_same_hazard_is_announced_once_per_cooldown(detector) -> None:
    stairs = looks_like("stairs")
    assert len(detector.check(stairs, T0)) == 1
    assert detector.check(stairs, T0 + timedelta(seconds=5)) == []  # same staircase
    assert len(detector.check(looks_like("closed_door"), T0 + timedelta(seconds=6))) == 1
    assert len(detector.check(stairs, T0 + timedelta(seconds=16))) == 1  # new staircase


def test_weak_evidence_does_not_warn(detector) -> None:
    """Barely closer to 'stairs' than to anything else: below the threshold."""
    assert detector.check(looks_like("stairs", strength=0.01), T0) == []


# ---------- slow: real CLIP on real photos ----------

COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/{}?width=640"
STAIRS_PHOTOS = ["A_staircase_to_first_floor.jpg", "Internal_staircase.jpg", "Staircase_1.jpg"]
DOOR_PHOTOS = ["Interior_door_19-10-12_056.jpg", "Closed_door_02.jpg"]


def commons_photo(name: str) -> np.ndarray:
    path = settings.models_path.parent / "test_images" / f"commons_{name}"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            COMMONS.format(urllib.parse.quote(name)),
            headers={"User-Agent": "voice-assistant-uni-project-tests/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                path.write_bytes(response.read())
        except OSError as exc:
            pytest.skip(f"cannot download test photo {name}: {exc}")
    return cv2.imread(str(path))


@pytest.fixture(scope="module")
def real():
    from app.memory.embeddings import Embedder

    embedder = Embedder()
    return embedder, hazards.HazardDetector(embedder, cooldown_s=0)


@pytest.mark.slow
@pytest.mark.parametrize("name", STAIRS_PHOTOS)
def test_real_stairs_warn(real, name) -> None:
    embedder, detector = real
    found = detector.check(embedder.embed_image(commons_photo(name)), T0)
    assert [h.kind for h in found] == ["stairs"]


@pytest.mark.slow
@pytest.mark.parametrize("name", DOOR_PHOTOS)
def test_real_closed_doors_warn(real, name) -> None:
    embedder, detector = real
    found = detector.check(embedder.embed_image(commons_photo(name)), T0)
    assert [h.kind for h in found] == ["closed_door"]


@pytest.mark.slow
def test_everyday_scenes_do_not_warn(real) -> None:
    import ultralytics

    from tests.vision.test_detect import COCO_LIVING_ROOM, _photo

    embedder, detector = real
    everyday = {
        "living room": cv2.imread(str(_photo("coco_000000000139.jpg", COCO_LIVING_ROOM))),
        "street": cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg")),
        "sign": signs.english(),
        "wall": scenes.wall(),
    }
    for name, image in everyday.items():
        assert detector.check(embedder.embed_image(image), T0) == [], name
