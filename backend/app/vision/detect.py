"""Object detection: what is in the frame and where (owner: Student A, task A6).

YOLOv8n (ultralytics) pre-trained on COCO: 80 everyday classes such as person,
chair, couch, table, door-adjacent things like suitcase or potted plant, bottle,
laptop, car, bicycle... It finds all objects in ONE pass over the image (hence
"You Only Look Once"), about 0.1 s per frame on a laptop CPU.

For a blind user the position matters as much as the label, so every object gets:
  position  "left" | "center" | "right": which third of the frame its centre is in
  near      True when the box covers more than near_area (25%) of the frame

Privacy: "person" is only a class label. Nothing here (or anywhere in the project)
tries to recognise WHO someone is.

Try it on your own photos:
    python -m app.vision.detect photo.jpg
"""

import logging
import sys
import time
from pathlib import Path

import numpy as np

from app.config import settings
from app.contracts import DetectedObject

log = logging.getLogger(__name__)


def position_of(bbox: list[int], frame_width: int) -> str:
    """Left / center / right third of the frame, from the box centre."""
    centre = (bbox[0] + bbox[2]) / 2
    if centre < frame_width / 3:
        return "left"
    if centre > 2 * frame_width / 3:
        return "right"
    return "center"


def is_near(bbox: list[int], frame_width: int, frame_height: int) -> bool:
    """A big box means the object is close to the camera."""
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    return area > settings.near_area * frame_width * frame_height


def make_object(label: str, confidence: float, bbox: list[int], width: int,
                height: int) -> DetectedObject:
    return DetectedObject(
        label=label,
        confidence=round(confidence, 3),
        bbox=bbox,
        position=position_of(bbox, width),
        near=is_near(bbox, width, height),
    )


class ObjectDetector:
    def __init__(self) -> None:
        from ultralytics import YOLO  # heavy import (PyTorch); only when really used

        weights = settings.models_path / settings.yolo_model
        weights.parent.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        # Given a path to a missing official file, ultralytics downloads it there (~6 MB)
        self.model = YOLO(str(weights))
        self.detect(np.full((480, 640, 3), 128, np.uint8))  # warm up: first call is slow
        log.info("YOLO %s loaded in %.1f s", settings.yolo_model, time.perf_counter() - start)

    def detect(self, image: np.ndarray) -> list[DetectedObject]:
        """Objects in one BGR frame, most confident first."""
        height, width = image.shape[:2]
        result = self.model.predict(
            image, conf=settings.detect_min_confidence, verbose=False, device="cpu"
        )[0]
        objects = [
            make_object(
                result.names[int(cls)], float(conf), [round(v) for v in box.tolist()],
                width, height,
            )
            for box, conf, cls in zip(
                result.boxes.xyxy, result.boxes.conf, result.boxes.cls, strict=True
            )
        ]
        return sorted(objects, key=lambda o: o.confidence, reverse=True)


if __name__ == "__main__":
    import cv2

    logging.basicConfig(level=logging.INFO)
    detector = ObjectDetector()
    for path in sys.argv[1:]:
        frame = cv2.imread(path)
        if frame is None:
            print(f"{path}: cannot read")
            continue
        t0 = time.perf_counter()
        found = detector.detect(frame)
        print(f"--- {Path(path).name} ({(time.perf_counter() - t0) * 1000:.0f} ms)")
        for obj in found:
            near = ", near" if obj.near else ""
            print(f"  {obj.confidence:.2f}  {obj.label} ({obj.position}{near})  {obj.bbox}")
