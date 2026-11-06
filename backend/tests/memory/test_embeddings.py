"""A7 slow tests: real CLIP embeddings put images and questions in one space, in 3 languages.

Run from backend/:  pytest tests/memory/test_embeddings.py -v -m slow
Uses two real photos: ultralytics' bus.jpg (a street with a bus) and COCO val2017
#139 (a living room), cached in data/test_images/ by the A6 tests.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from tests.vision.test_detect import COCO_LIVING_ROOM, _photo

pytestmark = pytest.mark.slow

QUERIES = {
    "bus": ["a bus on the street", "un bus dans la rue", "حافلة في الشارع"],
    "room": [
        "a living room with chairs and a TV",
        "un salon avec des chaises et une télévision",
        "غرفة جلوس فيها كراسي وتلفاز",
    ],
}


@pytest.fixture(scope="module")
def embedder():
    from app.memory.embeddings import Embedder

    return Embedder()


@pytest.fixture(scope="module")
def photos() -> dict[str, np.ndarray]:
    import ultralytics

    bus = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"
    room = _photo("coco_000000000139.jpg", COCO_LIVING_ROOM)
    return {"bus": cv2.imread(str(bus)), "room": cv2.imread(str(room))}


def test_vectors_are_512_dim_unit_length(embedder, photos) -> None:
    image_vec = embedder.embed_image(photos["bus"])
    text_vec = embedder.embed_text("Text: EXIT. Objects: door (center, near)")
    for vector in (image_vec, text_vec):
        assert vector.shape == (512,)
        assert vector.dtype == np.float32
        assert np.linalg.norm(vector) == pytest.approx(1.0, abs=1e-4)


@pytest.mark.parametrize("language", [0, 1, 2], ids=["en", "fr", "ar"])
def test_question_finds_the_right_photo_in_each_language(embedder, photos, language) -> None:
    """A question about a scene is closer to that scene's photo than to the other one."""
    image_vecs = {name: embedder.embed_image(img) for name, img in photos.items()}
    for scene, questions in QUERIES.items():
        query = embedder.embed_text(questions[language])
        scores = {name: float(query @ vec) for name, vec in image_vecs.items()}
        best = max(scores, key=scores.get)
        assert best == scene, f"{questions[language]!r} -> {scores}"


def test_same_meaning_in_three_languages_lands_close(embedder) -> None:
    en, fr, ar = (embedder.embed_text(t) for t in ("exit sign", "panneau de sortie", "لافتة مخرج"))
    unrelated = embedder.embed_text("a plate of spaghetti")
    assert en @ fr > en @ unrelated
    assert en @ ar > en @ unrelated
