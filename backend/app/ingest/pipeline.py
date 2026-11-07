"""Per-frame processing pipeline: the "Remember" step (owner: Student A).

Order: quality -> enhance -> face blur -> OCR -> objects -> embed -> store -> warnings.
Done: quality (A3), enhance (A4), OCR (A5), objects (A6), embed + store (A7), face blur (A9),
warnings (A11). Warnings are checked right after the image embedding, BEFORE the slow
OCR (~2 s), so the phone hears "stairs" as early as possible.
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
from app.vision.enhance import enhance
from app.vision.faces import FaceBlurrer
from app.vision.hazards import HazardDetector
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
        faces: FaceBlurrer | None = None,
        hazards: HazardDetector | None = None,
    ) -> None:
        self.selector = selector or FrameSelector()
        self.ocr = ocr or OcrEngine()
        self.detector = detector or ObjectDetector()
        self.embedder = embedder or Embedder()
        self.faces = faces or FaceBlurrer()
        self.hazards = hazards or HazardDetector(self.embedder)
        self.notifier = notifier  # None: store without sending events (tests, scripts)
        self.last_timings: dict[str, int] = {}  # ms per stage of the last stored frame (A12)
        self.last_frame_id: int | None = None

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

        # A4: a dark frame is brightened; OCR, CLIP, the stored JPEG (and so the dashboard
        # and the VLM) all use the enhanced image.
        enhanced = enhance(image, quality.brightness)
        image = enhanced.image
        lap("enhance")
        # A9: faces are pixelated before anything is stored or sent anywhere (privacy).
        # Detected on the enhanced image: faces in the dark are found more easily.
        blurred = self.faces.blur(image)
        image = blurred.image
        lap("faces")

        # A11: warn first (CLIP zero-shot on the image vector, ~1 ms), then the slow steps.
        # The id is reserved now so the warning can point to the frame being stored.
        image_emb = self.embedder.embed_image(image)
        frame_id = repo.reserve_frame_id()
        hazards = self.hazards.check(image_emb, frame.captured_at)
        if self.notifier is not None:
            for hazard in hazards:
                self.notifier.post("warning", hazard.event_data(frame_id))
        lap("warnings")

        ocr = self.ocr.read(image)
        lap("ocr")
        # YOLO reads the ORIGINAL frame: it was trained with brightness changes, and on our
        # dark test photos the enhanced image made it find fewer objects (A4 measurements).
        # Same size, so its boxes still fit the stored image. The original is never stored:
        # only labels and boxes come out of YOLO, no face.
        objects = self.detector.detect(frame.image)
        lap("objects")
        caption = build_caption(ocr.text, objects)
        text_emb = self.embedder.embed_text(caption) if caption else None  # nothing to say
        lap("embed")

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
                enhanced=enhanced.enhanced,
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

        self.last_timings, self.last_frame_id = ms, frame_id
        if self.notifier is not None:
            summary = repo.get_frame(frame_id).to_summary()
            self.notifier.post("frame_stored", summary.model_dump(mode="json"))
        log.info(
            "Stored frame %d (%s, %d face(s) blurred%s) caption=%r | %s",
            frame_id, decision.reason, len(blurred.faces),
            "".join(f", WARNING {h.kind} {h.confidence:.2f}" for h in hazards), caption,
            " ".join(f"{stage}={value}ms" for stage, value in ms.items()),
        )
        return True
