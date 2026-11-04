"""Per-frame processing pipeline (owner: Student A).

Final order (A7): quality -> enhance -> face blur -> OCR -> objects -> embed -> store -> warnings.
Done so far: quality (A3), OCR (A5), objects (A6). A7 adds the storage.
The heavy models are passed in (or loaded once here), never per frame.
"""

import logging

from app.ingest.grabber import GrabbedFrame
from app.vision.detect import ObjectDetector
from app.vision.ocr import OcrEngine
from app.vision.quality import FrameSelector, measure

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        selector: FrameSelector | None = None,
        ocr: OcrEngine | None = None,
        detector: ObjectDetector | None = None,
    ) -> None:
        self.selector = selector or FrameSelector()
        self.ocr = ocr or OcrEngine()
        self.detector = detector or ObjectDetector()

    def process(self, frame: GrabbedFrame) -> bool:
        """Analyse one sampled frame; True if it was kept (stored)."""
        quality = measure(frame.image)
        decision = self.selector.decide(quality, frame.captured_at)
        if not decision.keep:
            return False
        text = self.ocr.read(frame.image).text
        objects = self.detector.detect(frame.image)
        log.info(
            "Kept frame %d (%s): sharpness=%.0f text=%r objects=%s",
            frame.seq, decision.reason, quality.sharpness, text.replace("\n", " | "),
            ", ".join(f"{o.label} ({o.position}{', near' if o.near else ''})" for o in objects)
            or "none",
        )
        return True
