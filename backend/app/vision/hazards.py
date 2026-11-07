"""Warnings for stairs and closed doors ahead (owner: Student A, task A11, bonus).

How: CLIP ZERO-SHOT classification. The pipeline already has the CLIP image vector of
every kept frame (A7, for search); here it is compared with short sentences such as
"a photo of stairs" or "a photo of a closed door", plus many "everyday" sentences
("a photo of a room", "a photo of a street"...). A softmax over the similarities
gives a probability per kind; above its threshold, a `warning` event is sent:
    {kind: "closed_door" | "stairs", confidence, frame_id, position}
Student B's phone turns it into a spoken sentence in the user's language.
Extra cost per frame: one 512 x 20 matrix product, about 1 ms.

Why not YOLO-World (open-vocabulary YOLO)? Measured on 9 real photos from
Wikimedia Commons (3 closed doors, 5 staircases): YOLO-World-s found 0 of 5
staircases and gave doors 0.06-0.17. CLIP zero-shot: stairs 5/5 (0.74-0.98) and
doors 3/3 (0.46-0.83), while 11 everyday scenes stayed at or below 0.31 for stairs
and 0.37 for doors. Hence the thresholds 0.5 (stairs) and 0.45 (doors); the door
margin is thin, so a door warning is a hint, never a guarantee.

Position: the camera looks where the user walks, so a hazard in the frame is
"center" (ahead). Classifying left/middle/right strips was tried and gave the wrong
side on 2 of 9 photos for 0.8 s more, so it is not used.

Never "safe": no warning is NOT a promise that the way is clear (and the phone
never says so; see Student B's honesty rules).
"""

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.config import settings

PROMPTS: dict[str, list[str]] = {
    "closed_door": [
        "a photo of a closed door", "a closed door in front of me", "a photo of a door",
    ],
    "stairs": ["a photo of stairs", "a photo of a staircase", "steps going up or down"],
    # Everything else the camera usually sees: the probability mass goes here instead
    "other": [
        "a photo of a room", "a photo of a hallway", "a photo of a street",
        "a photo of a sign on a wall", "a photo of an open door", "a photo of people",
        "a photo of furniture", "a photo of a wall", "a photo of a window", "a painting",
        "a photo of a shop",
    ],
}
KINDS = ("closed_door", "stairs")
LOGIT_SCALE = 100.0  # CLIP's own temperature: turns cosine similarities into a sharp softmax


@dataclass
class Hazard:
    kind: str  # "closed_door" | "stairs"
    confidence: float  # 0..1
    position: str = "center"

    def event_data(self, frame_id: int) -> dict:
        """Payload of the `warning` event (contract)."""
        return {"kind": self.kind, "confidence": round(self.confidence, 3),
                "frame_id": frame_id, "position": self.position}


class HazardDetector:
    def __init__(self, embedder, thresholds: dict[str, float] | None = None,
                 cooldown_s: float | None = None) -> None:
        """`embedder` is the pipeline's Embedder (its CLIP text side encodes the prompts)."""
        self.labels = [kind for kind, prompts in PROMPTS.items() for _ in prompts]
        sentences = [prompt for prompts in PROMPTS.values() for prompt in prompts]
        self.prompt_vectors = embedder.embed_prompts(sentences)  # (20, 512), unit length
        self.thresholds = thresholds or {
            "closed_door": settings.warn_door_min, "stairs": settings.warn_stairs_min,
        }
        self.cooldown_s = settings.warning_cooldown_s if cooldown_s is None else cooldown_s
        self._last_warned: dict[str, datetime] = {}

    def probabilities(self, image_emb: np.ndarray) -> dict[str, float]:
        """Softmax over all prompts, summed per kind (closed_door, stairs, other)."""
        logits = LOGIT_SCALE * (self.prompt_vectors @ image_emb)
        weights = np.exp(logits - logits.max())
        weights /= weights.sum()
        result = dict.fromkeys(PROMPTS, 0.0)
        for label, weight in zip(self.labels, weights, strict=True):
            result[label] += float(weight)
        return result

    def check(self, image_emb: np.ndarray, captured_at: datetime) -> list[Hazard]:
        """Hazards to announce now: above threshold and not announced in the last cooldown_s.

        The same staircase stays in view for several kept frames; it is announced once.
        """
        probabilities = self.probabilities(image_emb)
        hazards = []
        for kind in KINDS:
            confidence = probabilities[kind]
            if confidence < self.thresholds[kind]:
                continue
            last = self._last_warned.get(kind)
            if last is not None and (captured_at - last).total_seconds() < self.cooldown_s:
                continue
            self._last_warned[kind] = captured_at
            hazards.append(Hazard(kind, confidence))
        return hazards
