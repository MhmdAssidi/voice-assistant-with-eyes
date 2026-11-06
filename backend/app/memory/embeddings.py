"""CLIP embeddings: the "meaning" of frames and questions as 512 numbers (owner: Student A, A7).

CLIP (OpenAI) was trained on millions of image-caption pairs so that a picture and
a sentence describing it end up close together in the same 512-dim space. We use:
  clip-ViT-B-32                     images  -> image_emb
  clip-ViT-B-32-multilingual-v1     text    -> text_emb (caption) and, in A8, questions
The multilingual model was trained to land on the SAME points as the original
English CLIP text model for 50+ languages, so "exit sign", "panneau de sortie" and
"لافتة مخرج" all point close to a photo of an exit sign.

Vectors are L2-normalised (length 1), so cosine similarity is a dot product and
pgvector's cosine distance (<=>) ranks them directly.
Both models (~1.1 GB together) download once to MODELS_DIR/sentence-transformers.
"""

import logging
import time

import cv2
import numpy as np
from PIL import Image

from app.config import settings
from app.contracts import DetectedObject

log = logging.getLogger(__name__)

IMAGE_MODEL = "clip-ViT-B-32"
TEXT_MODEL = "sentence-transformers/clip-ViT-B-32-multilingual-v1"
DIM = 512


def build_caption(ocr_text: str, objects: list[DetectedObject]) -> str:
    """Short text summary of a frame, embedded as text_emb and shown to the VLM.

    Example: "Text: SORTIE EXIT. Objects: door (center, near), chair (left)"
    Empty string when the frame has no text and no objects.
    """
    parts = []
    text = " ".join(ocr_text.split())  # one line, single spaces
    if text:
        parts.append(f"Text: {text}.")
    described = []
    for obj in objects:
        words = f"{obj.label} ({obj.position}{', near' if obj.near else ''})"
        if words not in described:  # four chairs in the middle: say it once
            described.append(words)
    if described:
        parts.append(f"Objects: {', '.join(described)}")
    return " ".join(parts)


class Embedder:
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # heavy (PyTorch)

        cache = str(settings.models_path / "sentence-transformers")
        start = time.perf_counter()
        self.image_model = SentenceTransformer(IMAGE_MODEL, cache_folder=cache, device="cpu")
        self.text_model = SentenceTransformer(TEXT_MODEL, cache_folder=cache, device="cpu")
        self.embed_text("warm up")  # first call is slow
        log.info("CLIP models loaded in %.1f s", time.perf_counter() - start)

    def embed_image(self, image: np.ndarray) -> np.ndarray:
        """512-dim unit vector for a BGR frame."""
        rgb = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        vector = self.image_model.encode(rgb, normalize_embeddings=True, convert_to_numpy=True)
        return vector.astype(np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        """512-dim unit vector for a caption or a question, in any of our languages."""
        vector = self.text_model.encode(text, normalize_embeddings=True, convert_to_numpy=True)
        return vector.astype(np.float32)
