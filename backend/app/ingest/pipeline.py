"""Per-frame processing pipeline (owner: Student A).

Final order (A7): quality -> enhance -> face blur -> OCR -> objects -> embed -> store -> warnings.
Done so far: quality (A3). A7 adds the storage.
"""

import logging

from app.ingest.grabber import GrabbedFrame
from app.vision.quality import FrameSelector, measure

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, selector: FrameSelector | None = None) -> None:
        self.selector = selector or FrameSelector()

    def process(self, frame: GrabbedFrame) -> bool:
        """Analyse one sampled frame; True if it was kept (stored)."""
        quality = measure(frame.image)
        decision = self.selector.decide(quality, frame.captured_at)
        if not decision.keep:
            return False
        log.info(
            "Kept frame %d (%s): sharpness=%.0f brightness=%.0f informative=%.3f",
            frame.seq, decision.reason, quality.sharpness, quality.brightness,
            quality.informativeness,
        )
        return True
