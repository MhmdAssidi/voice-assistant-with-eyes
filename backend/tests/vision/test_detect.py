"""A6 tests: object positions (fast) and real YOLO detection (slow).

Run from backend/:
    pytest tests/vision/test_detect.py -v             # fast tests only (CI)
    pytest tests/vision/test_detect.py -v -m slow     # also runs YOLOv8n on real photos

The slow tests use real photos, not drawings (YOLO is trained on photos):
- bus.jpg, shipped inside the ultralytics package (works offline);
- COCO val2017 image 139 (a living room with chairs and a person), downloaded
  once from images.cocodataset.org into data/test_images/.
"""

import urllib.request
from pathlib import Path

import cv2
import pytest

from app.config import settings
from app.vision.detect import is_near, make_object, position_of

W, H = 640, 480
COCO_LIVING_ROOM = "http://images.cocodataset.org/val2017/000000000139.jpg"


# ---------- fast: position and distance words ----------

def test_position_from_box_centre() -> None:
    assert position_of([0, 0, 100, 100], W) == "left"  # centre x = 50
    assert position_of([270, 0, 370, 100], W) == "center"  # centre x = 320
    assert position_of([540, 0, 640, 100], W) == "right"  # centre x = 590
    # A wide box is placed by its centre, not by its edges
    assert position_of([0, 0, 640, 100], W) == "center"


def test_near_when_box_covers_more_than_a_quarter_of_the_frame() -> None:
    assert is_near([0, 0, 640, 480], W, H)  # whole frame
    assert is_near([0, 0, 400, 240], W, H)  # 31% of the frame
    assert not is_near([0, 0, 320, 240], W, H)  # exactly 25%: not more than
    assert not is_near([100, 100, 150, 200], W, H)  # small and far


def test_make_object_matches_the_contract() -> None:
    obj = make_object("chair", 0.8567, [20, 300, 180, 470], W, H)
    assert obj.label == "chair"
    assert obj.confidence == 0.857
    assert obj.position == "left"
    assert obj.near is False


# ---------- slow: real YOLOv8n ----------

@pytest.fixture(scope="module")
def detector():
    from app.vision.detect import ObjectDetector

    return ObjectDetector()


def _photo(name: str, url: str) -> Path:
    path = settings.models_path.parent / "test_images" / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(url, path)
        except OSError as exc:
            pytest.skip(f"cannot download test photo {url}: {exc}")
    return path


@pytest.mark.slow
def test_chair_and_person_with_positions(detector) -> None:
    """A6 done-test: a photo with a chair and a person returns both with positions."""
    image = cv2.imread(str(_photo("coco_000000000139.jpg", COCO_LIVING_ROOM)))
    objects = detector.detect(image)
    labels = {o.label for o in objects}
    assert {"chair", "person"} <= labels

    person = next(o for o in objects if o.label == "person")
    assert person.position == "right"  # standing in the right third of the room
    chair = max((o for o in objects if o.label == "chair"), key=lambda o: o.confidence)
    assert chair.position == "center"
    assert all(o.confidence >= settings.detect_min_confidence for o in objects)


@pytest.mark.slow
def test_bus_photo_people_left_center_right(detector) -> None:
    import ultralytics

    image = cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg"))
    objects = detector.detect(image)
    bus = next(o for o in objects if o.label == "bus")
    assert bus.near is True  # fills most of the photo
    people = {o.position for o in objects if o.label == "person"}
    assert people == {"left", "center", "right"}


@pytest.mark.slow
def test_blank_wall_has_no_objects(detector) -> None:
    from tests.vision import scenes

    assert detector.detect(scenes.wall()) == []
