"""Speech-to-text with faster-whisper (owner: Student B, task B6).

Whisper turns the recorded question into text and tells which language was
spoken. The model is loaded once (the first call takes a few seconds; the very
first run also downloads it, ~480 MB for "small", into MODELS_DIR).
"""

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, BinaryIO

import numpy as np

from app.assistant.i18n import SUPPORTED_LANGUAGES
from app.config import settings
from app.contracts import Language

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

SAMPLE_RATE = 16000  # Whisper works on 16 kHz mono audio

# Language choice (see choose_language): trust Whisper alone only when it is
# very sure; otherwise the app's language wins if Whisper finds it plausible.
SURE = 0.90
PLAUSIBLE = 0.05


@dataclass(frozen=True)
class Transcript:
    text: str  # "" when no speech was found
    language: Language  # always en, fr or ar: the language we answer in
    detected_language: str  # Whisper's own best guess, may be another language
    language_probability: float  # Whisper's probability for `detected_language`
    duration_s: float  # length of the audio


_model: "WhisperModel | None" = None
_model_lock = threading.Lock()


def get_model() -> "WhisperModel":
    """Loads the Whisper model once and reuses it for every question."""
    global _model
    with _model_lock:
        if _model is None:
            # Imported here so the API starts fast and tests that fake the
            # model never load the heavy library.
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                settings.whisper_model,  # "small", or a folder with the model files
                device="cpu",
                compute_type="int8",  # 8-bit weights: ~4x less memory, faster on CPU
                download_root=str(settings.models_path),
            )
    return _model


def decode_audio(audio: str | BinaryIO) -> np.ndarray:
    """Any audio file (m4a, wav, ...) -> 16 kHz mono float32 samples in [-1, 1].

    Our own small decoder instead of faster_whisper.decode_audio, which calls
    PyAV with an option (metadata_errors) that PyAV 17+ removed.
    """
    import av

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks: list[np.ndarray] = []
    with av.open(audio, mode="r") as container:
        for frame in container.decode(audio=0):
            chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(frame)]
        chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(None)]  # flush
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def fallback_language(lang_hint: str | None) -> Language:
    """The app's language if valid, else English."""
    return lang_hint if lang_hint in SUPPORTED_LANGUAGES else "en"  # type: ignore[return-value]


def choose_language(probabilities: list[tuple[str, float]], lang_hint: str | None) -> Language:
    """Picks en, fr or ar from Whisper's language probabilities.

    Whisper's guess is unreliable on short questions with an accent (in testing,
    an English question with a Lebanese accent came out 80 % Arabic, 14 % English).
    So: if Whisper is very sure, follow it; otherwise prefer the app's language
    (lang_hint) as long as Whisper finds it plausible; otherwise Whisper's best
    guess among our three languages.
    """
    probs = {lang: p for lang, p in probabilities if lang in SUPPORTED_LANGUAGES}
    if not probs:
        return fallback_language(lang_hint)
    best = max(probs, key=lambda lang: probs[lang])
    if probs[best] >= SURE:
        return best  # type: ignore[return-value]
    if lang_hint in probs and probs[lang_hint] >= PLAUSIBLE:
        return lang_hint  # type: ignore[return-value]
    return best  # type: ignore[return-value]


def transcribe(audio: str | BinaryIO, lang_hint: str | None = None) -> Transcript:
    """Transcribes a recording (file path or file-like object)."""
    samples = decode_audio(audio)
    duration = round(len(samples) / SAMPLE_RATE, 2)
    model = get_model()

    # 1) Which language? (one pass of the model over the speech parts)
    try:
        detected, probability, all_probs = model.detect_language(samples, vad_filter=True)
    except ValueError:
        # The voice filter found no speech at all (silence, noise): nothing to transcribe.
        language = fallback_language(lang_hint)
        return Transcript("", language, language, 0.0, duration)
    language = choose_language(all_probs, lang_hint)

    # 2) Transcribe in that language. vad_filter skips silence: faster, and it
    #    stops Whisper from "hearing" words in background noise.
    segments, _ = model.transcribe(samples, language=language, vad_filter=True, beam_size=5)
    # segments is a generator: the real work happens while we join the texts
    text = " ".join(segment.text.strip() for segment in segments).strip()

    return Transcript(
        text=text,
        language=language,
        detected_language=detected,
        language_probability=round(probability, 3),
        duration_s=duration,
    )
