"""Instructions given to the vision-language model (owner: Student B, task B7).

The system prompt carries the project's answer rules; the user prompt lists
the question and, for each evidence image, its age, OCR text and objects.
"""

from dataclasses import dataclass

LANGUAGE_NAMES = {"en": "English", "fr": "French", "ar": "Arabic"}

SYSTEM_PROMPT = """You are the eyes of a blind or visually impaired person. \
They ask a short spoken question; you see up to 3 recent photos from the camera \
they carry, with the text and objects already detected in each photo.

Rules (always follow all of them):
1. Use ONLY what is in the photos and the detected text/objects given. Never invent \
or guess anything that is not visible.
2. Answer in at most 2 short sentences, simple words, ready to be read aloud.
3. Write the answer in {language_name}.
4. Never identify or describe a person's identity, face or appearance; just say \
"a person" (or "people").
5. Never say that something is safe, or that it is safe to go, cross, or move.
6. If the photos do not clearly show the answer, set "confident" to false and \
start the answer by saying you are not sure.
7. For questions about what is in front of the user right now, use the newest photo. \
For questions about earlier ("before", "just passed"), describe the earlier photos. \
Use positions (left, center, right, near) when they help.
8. The answer is read aloud by a voice that only speaks {language_name}: if a sign or \
label is written in another language, say what it means in {language_name} instead of \
copying the foreign words.

Reply with JSON only: {{"answer": "<text>", "confident": true or false}}"""


@dataclass(frozen=True)
class PromptImage:
    """What we know about one evidence photo."""

    age_s: int  # seconds since it was captured
    ocr_text: str | None  # None = not analysed (live snapshot): the model reads the picture
    objects: list[str] | None  # e.g. ["door (center, near)", "chair (left)"]; None = not analysed
    is_latest: bool  # the newest view of the camera
    has_image: bool  # False if the JPEG file is missing


def system_prompt(language: str) -> str:
    return SYSTEM_PROMPT.format(language_name=LANGUAGE_NAMES.get(language, "English"))


def user_prompt(question: str, images: list[PromptImage]) -> str:
    lines = [f"Question: {question}", ""]
    if not images:
        lines.append("No photos are available.")
    for number, image in enumerate(images, start=1):
        kind = "newest view" if image.is_latest else "earlier view"
        lines.append(f"Photo {number} ({kind}, taken {_age(image.age_s)} ago):")
        if not image.has_image:
            lines.append("  (picture not available; use only the description below)")
        if image.ocr_text is None and image.objects is None:
            lines.append("  (taken right now; read any text and objects from the picture itself)")
            continue
        lines.append(f"  Text read in it: {image.ocr_text or '(none)'}")
        lines.append(f"  Objects detected: {', '.join(image.objects or []) or '(none)'}")
    return "\n".join(lines)


def _age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} s"
    return f"{seconds // 60} min {seconds % 60} s"
