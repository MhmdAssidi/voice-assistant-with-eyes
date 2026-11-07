"""CLIP embeddings: the "meaning" of frames and questions as 512 numbers (owner: Student A, A7).

CLIP (OpenAI) was trained on millions of image-caption pairs so that a picture and
a sentence describing it end up close together in the same 512-dim space. We use:
  clip-ViT-B-32                     images  -> image_emb
  clip-ViT-B-32-multilingual-v1     text    -> text_emb (caption) and questions (A8 search)
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


MAX_CAPTION_OBJECTS = 6  # a long list of labels drowns the meaning


def _join_words(words: list[str]) -> str:
    """["a tv", "a chair", "a person"] -> "a tv, a chair and a person"."""
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def build_caption(ocr_text: str, objects: list[DetectedObject]) -> str:
    """Short sentence describing a frame, embedded as text_emb.

    Examples:
        'a sign that says "SORTIE EXIT"'
        'a photo of a door and a chair'
        'a photo of a door and a chair, with a sign that says "SORTIE EXIT"'
    Empty string when the frame has no text and no objects.

    Written like the captions CLIP was trained on (A8 calibration): with the old
    "Text: X. Objects: Y" format every caption looked alike to the text model, and
    "a chair and a tv" even scored LOWEST on the living-room frame.
    Positions (left/center/right, near) stay in the `objects` column.
    """
    text = " ".join(ocr_text.split())  # one line, single spaces
    labels = list(dict.fromkeys(obj.label for obj in objects))[:MAX_CAPTION_OBJECTS]
    sign = f'a sign that says "{text}"' if text else ""
    if not labels:
        return sign
    photo = "a photo of " + _join_words(
        [f"{'an' if label[0] in 'aeiou' else 'a'} {label}" for label in labels]
    )
    return f"{photo}, with {sign}" if sign else photo


class Embedder:
    def __init__(self, with_image_model: bool = True) -> None:
        """The ingest worker needs both models; search (A8) only embeds questions,
        so the API loads the text model alone (faster start, ~600 MB less memory)."""
        from sentence_transformers import SentenceTransformer  # heavy (PyTorch)

        cache = str(settings.models_path / "sentence-transformers")
        start = time.perf_counter()
        self.image_model = (
            SentenceTransformer(IMAGE_MODEL, cache_folder=cache, device="cpu")
            if with_image_model else None
        )
        self.text_model = SentenceTransformer(TEXT_MODEL, cache_folder=cache, device="cpu")
        self.embed_text("warm up")  # first call is slow
        log.info("CLIP models loaded in %.1f s", time.perf_counter() - start)

    def embed_image(self, image: np.ndarray) -> np.ndarray:
        """512-dim unit vector for a BGR frame."""
        if self.image_model is None:
            raise RuntimeError("This Embedder was created without the image model")
        rgb = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        vector = self.image_model.encode(rgb, normalize_embeddings=True, convert_to_numpy=True)
        return vector.astype(np.float32)

    def embed_prompts(self, texts: list[str]) -> np.ndarray:
        """English CLIP text vectors (the image model's own text side), for zero-shot
        classification of frames (A11 warnings). Shape (len(texts), 512), unit length."""
        if self.image_model is None:
            raise RuntimeError("This Embedder was created without the image model")
        vectors = self.image_model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vectors.astype(np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        """512-dim unit vector for a caption or a question, in any of our languages."""
        vector = self.text_model.encode(text, normalize_embeddings=True, convert_to_numpy=True)
        return vector.astype(np.float32)
