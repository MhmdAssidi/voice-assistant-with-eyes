"""Per-frame processing pipeline: the "Remember" step (owner: Student A).

Order: quality -> enhance -> face blur -> OCR -> objects -> embed -> store -> warnings.
Done: quality (A3), OCR (A5), objects (A6), embed + store (A7).
Coming in Week 4: enhance (A4), face blur (A9), warnings (A11).
The heavy models are passed in (or loaded once here), never per frame.
"""

import logging
import time

from app.ingest.grabber import GrabbedFrame
from app.ingest.notifier import EventNotifier
from app.memory import files
from app.memory import repository as repo
from app.memory.embeddings import Embedder, build_caption
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
        embedder: Embedder | None = None,
        notifier: EventNotifier | None = None,
    ) -> None:
        self.selector = selector or FrameSelector()
        self.ocr = ocr or OcrEngine()
        self.detector = detector or ObjectDetector()
        self.embedder = embedder or Embedder()
        self.notifier = notifier  # None: store without sending events (tests, scripts)

    def process(self, frame: GrabbedFrame) -> bool:
        """Analyse one sampled frame; True if it was kept and stored."""
        ms: dict[str, int] = {}
        clock = time.perf_counter()

        def lap(stage: str) -> None:
            nonlocal clock
            now = time.perf_counter()
            ms[stage] = round((now - clock) * 1000)
            clock = now

        image = frame.image
        quality = measure(image)
        decision = self.selector.decide(quality, frame.captured_at)
        if not decision.keep:
            return False
        lap("quality")
        # A4 (enhance) and A9 (face blur) will change `image` here, before anything reads it

        ocr = self.ocr.read(image)
        lap("ocr")
        objects = self.detector.detect(image)
        lap("objects")
        caption = build_caption(ocr.text, objects)
        image_emb = self.embedder.embed_image(image)
        text_emb = self.embedder.embed_text(caption) if caption else None  # nothing to say
        lap("embed")

        frame_id = repo.reserve_frame_id()
        image_path, thumb_path = files.save_frame_images(frame_id, image)
        try:
            repo.insert_frame(repo.NewFrame(
                id=frame_id,
                captured_at=frame.captured_at,
                image_path=image_path,
                thumb_path=thumb_path,
                width=image.shape[1],
                height=image.shape[0],
                sharpness=quality.sharpness,
                brightness=quality.brightness,
                enhanced=False,
                dhash=quality.dhash,
                ocr_text=ocr.text,
                ocr_blocks=ocr.blocks,
                objects=objects,
                caption_text=caption,
                image_emb=image_emb,
                text_emb=text_emb,
            ))
        except Exception:
            files.delete_files(image_path, thumb_path)  # no orphan files without a row
            raise
        lap("store")

        if self.notifier is not None:
            summary = repo.get_frame(frame_id).to_summary()
            self.notifier.post("frame_stored", summary.model_dump(mode="json"))
        log.info(
            "Stored frame %d (%s) caption=%r | %s",
            frame_id, decision.reason, caption,
            " ".join(f"{stage}={value}ms" for stage, value in ms.items()),
        )
        return True
