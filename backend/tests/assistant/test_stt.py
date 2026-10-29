"""Speech-to-text tests (B6).

Fast tests use a fake Whisper model. The slow tests run the real model on
three recordings (one per language) in tests/assistant/audio/:
    pytest -m slow tests/assistant/test_stt.py -s
"""

import io
import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.assistant import stt
from app.main import app

AUDIO_DIR = Path(__file__).parent / "audio"


class FakeWhisper:
    """Answers like faster-whisper's detect_language() and transcribe()."""

    def __init__(self, probs: list[tuple[str, float]], text_by_language: dict[str, str]) -> None:
        self.probs = probs
        self.text_by_language = text_by_language
        self.transcribed_in: list[str] = []

    def detect_language(self, audio, vad_filter=False):  # noqa: ANN001, ANN201
        if not self.text_by_language:
            raise ValueError("need at least one array to concatenate")  # like real VAD: no speech
        return self.probs[0][0], self.probs[0][1], self.probs

    def transcribe(self, audio, language=None, **kwargs):  # noqa: ANN001, ANN201
        self.transcribed_in.append(language)
        text = self.text_by_language.get(language, "")
        segments = iter([SimpleNamespace(text=f" {text} ")] if text else [])
        return segments, SimpleNamespace(language=language)


@pytest.fixture
def fake_model(monkeypatch):  # noqa: ANN201
    """Replaces the real model and decoder; returns a function to set what it hears."""
    monkeypatch.setattr(stt, "decode_audio", lambda audio: np.zeros(32000, dtype=np.float32))

    def install(probs: list[tuple[str, float]], text_by_language: dict[str, str]) -> FakeWhisper:
        model = FakeWhisper(probs, text_by_language)
        monkeypatch.setattr(stt, "get_model", lambda: model)
        return model

    return install


# ---------- choosing the language ----------


@pytest.mark.parametrize(
    ("probs", "hint", "expected"),
    [
        ([("fr", 0.97), ("en", 0.02)], "en", "fr"),  # Whisper very sure -> follow it
        ([("ar", 0.80), ("en", 0.14)], "en", "en"),  # real case: accented English -> app language
        ([("ar", 0.80), ("en", 0.14)], "ar", "ar"),  # same audio, app in Arabic -> Arabic
        ([("ar", 0.80), ("en", 0.02)], "en", "ar"),  # app language not plausible -> best guess
        ([("es", 0.70), ("fr", 0.20), ("en", 0.05)], None, "fr"),  # best of our three
        ([("es", 0.99)], "ar", "ar"),  # none of our languages -> app language
        ([("de", 0.99)], None, "en"),  # ... or English
    ],
)
def test_choose_language(probs, hint, expected) -> None:  # noqa: ANN001
    assert stt.choose_language(probs, hint) == expected


# ---------- transcribe() with a fake model ----------


def test_transcribes_in_the_chosen_language(fake_model) -> None:
    model = fake_model([("ar", 0.80), ("en", 0.14)], {"en": "What's in front of me?"})
    t = stt.transcribe(io.BytesIO(b"audio"), lang_hint="en")
    assert (t.text, t.language, t.detected_language) == ("What's in front of me?", "en", "ar")
    assert model.transcribed_in == ["en"], "transcribed once, in the chosen language"
    assert t.duration_s == 2.0


def test_silence_gives_empty_text(fake_model) -> None:
    fake_model([("en", 0.5)], {})
    t = stt.transcribe(io.BytesIO(b"audio"), lang_hint="fr")
    assert t.text == ""
    assert t.language == "fr"


# ---------- decoding real audio bytes ----------


def test_decode_audio_resamples_to_16k_mono() -> None:
    # 1 second of a 440 Hz tone, 44.1 kHz stereo WAV, built in memory
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        tone = (int(8000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(44100))
        wav.writeframes(b"".join(struct.pack("<hh", s, s) for s in tone))
    buffer.seek(0)

    samples = stt.decode_audio(buffer)
    assert samples.dtype == np.float32
    assert abs(len(samples) - 16000) < 400  # ~1 s at 16 kHz
    assert 0.1 < np.abs(samples).max() <= 1.0


# ---------- /api/ask ----------


def test_ask_uses_the_transcript(fake_model) -> None:
    fake_model([("fr", 0.95)], {"fr": "Que dit ce panneau ?"})
    files = {"audio": ("question.m4a", b"audio-bytes", "audio/mp4")}
    r = TestClient(app).post("/api/ask", files=files, data={"lang_hint": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["question"] == "Que dit ce panneau ?"
    assert body["language"] == "fr"
    assert set(body["timings_ms"]) == {"stt", "search", "vlm", "total"}


def test_ask_with_silence_asks_again_in_the_language(fake_model) -> None:
    fake_model([("ar", 0.9)], {})
    files = {"audio": ("question.m4a", b"audio-bytes", "audio/mp4")}
    r = TestClient(app).post("/api/ask", files=files, data={"lang_hint": "ar"})
    assert r.status_code == 200
    assert r.json()["answer"] == "لم أسمع سؤالاً. انقر واطرح سؤالك مرة أخرى."


def test_ask_with_unreadable_audio_is_a_400() -> None:
    files = {"audio": ("question.m4a", b"this is not audio", "audio/mp4")}
    assert TestClient(app).post("/api/ask", files=files).status_code == 400


# ---------- Real model (slow): one recording per language ----------

RECORDINGS = [
    # file, app language (lang_hint), expected language, words that must appear (lower-case)
    ("en.m4a", "en", "en", ["front"]),
    ("fr.m4a", "en", "fr", ["devant"]),
    ("ar.m4a", "en", "ar", ["أمام"]),
]


@pytest.mark.slow
@pytest.mark.parametrize(("filename", "hint", "language", "words"), RECORDINGS)
def test_real_recordings(filename: str, hint: str, language: str, words: list[str]) -> None:
    path = AUDIO_DIR / filename
    if not path.exists():
        pytest.skip(f"record {path.name} first (see tests/assistant/audio/README.md)")
    t = stt.transcribe(str(path), lang_hint=hint)
    print(f"\n{filename}: [{t.language}, detected {t.detected_language} "
          f"p={t.language_probability}] {t.text!r}")
    assert t.language == language
    assert all(word in t.text.lower() for word in words), t.text
