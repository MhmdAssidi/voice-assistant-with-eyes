"""Per-frame processing pipeline (owner: Student A).

Final order (A7): quality -> enhance -> face blur -> OCR -> objects -> embed -> store -> warnings.
A2 placeholder: keeps nothing. A3 adds the quality filter, A7 the storage.
"""

from app.ingest.grabber import GrabbedFrame


class Pipeline:
    def process(self, frame: GrabbedFrame) -> bool:
        """Analyse one sampled frame; True if it was kept (stored)."""
        return False
