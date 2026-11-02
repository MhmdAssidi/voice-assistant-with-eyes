"""Answer pipeline tests (B7), with a fake vision-language model.

The real Gemini call is tested by hand / in a slow test (needs a key).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.assistant import answer, prompts, vlm
from app.assistant.i18n import NO_EVIDENCE, VLM_UNAVAILABLE
from app.contracts import DetectedObject, FrameDetail, FrameSummary, SearchHit
from app.main import app
from app.memory import search


class FakeProvider:
    name = "fake"

    def __init__(self, reply: vlm.VlmAnswer | Exception) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str, list[bytes]]] = []

    def generate(self, system: str, user: str, images: list[bytes]) -> vlm.VlmAnswer:
        self.calls.append((system, user, images))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def provider(monkeypatch):  # noqa: ANN201
    fake = FakeProvider(vlm.VlmAnswer(answer="A door with an EXIT sign, ahead.", confident=True))
    monkeypatch.setattr(answer, "get_provider", lambda: fake)
    return fake


def frame(frame_id: int, seconds_ago: int, ocr: str, labels: list[str]) -> FrameDetail:
    return FrameDetail(
        id=frame_id,
        captured_at=datetime.now(UTC) - timedelta(seconds=seconds_ago),
        thumb_url=f"/media/thumbs/{frame_id}.jpg",
        image_url=f"/media/frames/{frame_id}.jpg",
        ocr_text=ocr,
        object_labels=labels,
        enhanced=False,
        width=640,
        height=480,
        sharpness=150.0,
        brightness=120.0,
        ocr_blocks=[],
        objects=[
            DetectedObject(label=label, confidence=0.9, bbox=[0, 0, 10, 10],
                           position="center", near=True)
            for label in labels
        ],
    )


def hit(f: FrameDetail, score: float) -> SearchHit:
    summary = FrameSummary(**f.model_dump(include=set(FrameSummary.model_fields)))
    return SearchHit(frame=summary, score=score, matched_by=["text"])


@pytest.fixture
def memory(monkeypatch, tmp_path):  # noqa: ANN201
    """Latest frame 7 + search hits 7 (duplicate), 5, 4, 3; only frame 5 has a JPEG file."""
    latest = frame(7, 2, "EXIT", ["door"])
    others = [frame(5, 40, "Pharmacie", ["sign"]), frame(4, 90, "", ["chair"]),
              frame(3, 200, "Bus 12", ["bus"])]
    (tmp_path / "5.jpg").write_bytes(b"\xff\xd8 jpeg 5")
    monkeypatch.setattr(search, "get_latest_frame", lambda max_age_s=10: latest)
    hits = [hit(latest, 0.9)] + [hit(f, 0.5) for f in others]
    monkeypatch.setattr(search, "search_frames", lambda q, since=None, until=None, limit=5: hits)
    monkeypatch.setattr(search, "get_frame_image_path", lambda i: str(tmp_path / f"{i}.jpg"))
    return latest, others


# ---------- evidence ----------


def test_evidence_is_latest_then_best_hits_without_duplicates(memory) -> None:
    evidence = answer.gather_evidence("what is in front of me?")
    assert [e.frame.id for e in evidence] == [7, 5, 4]  # max 3, frame 7 not repeated
    assert evidence[0].is_latest and evidence[0].objects == ["door (center, near)"]
    assert [e.jpeg is not None for e in evidence] == [False, True, False]


def test_no_latest_frame_uses_search_only(memory, monkeypatch) -> None:
    monkeypatch.setattr(search, "get_latest_frame", lambda max_age_s=10: None)
    assert [e.frame.id for e in answer.gather_evidence("q")] == [7, 5, 4]


# ---------- answering ----------


def test_answer_uses_the_model_and_returns_evidence(memory, provider) -> None:
    result = answer.answer_question("What does the sign say?", "fr")
    assert result.answer == "A door with an EXIT sign, ahead."
    assert result.confident is True
    assert [e.frame_id for e in result.evidence] == [7, 5, 4]
    assert set(result.timings_ms) == {"search", "vlm"}

    system, user, images = provider.calls[0]
    assert "French" in system
    assert images == [b"\xff\xd8 jpeg 5"], "only frames whose JPEG exists are sent"
    assert "Question: What does the sign say?" in user
    assert "Text read in it: EXIT" in user and "Pharmacie" in user
    assert "newest view" in user and "picture not available" in user


def test_no_evidence_does_not_call_the_model(provider, monkeypatch) -> None:
    monkeypatch.setattr(search, "get_latest_frame", lambda max_age_s=10: None)
    monkeypatch.setattr(search, "search_frames", lambda q, since=None, until=None, limit=5: [])
    result = answer.answer_question("what is in front of me?", "ar")
    assert result.answer == NO_EVIDENCE["ar"]
    assert result.confident is False
    assert provider.calls == []


def test_model_failure_gives_a_spoken_apology(memory, monkeypatch) -> None:
    fake = FakeProvider(vlm.VlmError("429 quota exceeded"))
    monkeypatch.setattr(answer, "get_provider", lambda: fake)
    result = answer.answer_question("what is in front of me?", "en")
    assert result.answer == VLM_UNAVAILABLE["en"]
    assert result.confident is False
    assert len(result.evidence) == 3


def test_ask_endpoint_returns_the_model_answer(memory, provider) -> None:
    question = {"text": "What is in front of me?", "lang_hint": "en"}
    r = TestClient(app).post("/api/ask", data=question)
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "A door with an EXIT sign, ahead."
    assert body["confident"] is True
    assert [e["frame_id"] for e in body["evidence"]] == [7, 5, 4]
    assert set(body["timings_ms"]) == {"stt", "search", "vlm", "total"}


# ---------- prompts and model replies ----------


def test_system_prompt_contains_the_answer_rules() -> None:
    text = prompts.system_prompt("ar")
    assert "Arabic" in text
    assert "at most 2 short sentences" in text
    assert "a person" in text
    assert "Never say that something is safe" in text
    assert '"confident"' in text


@pytest.mark.parametrize(
    "reply",
    ['{"answer": "Hi.", "confident": true}', '```json\n{"answer": "Hi.", "confident": true}\n```'],
)
def test_parse_answer(reply: str) -> None:
    assert vlm.parse_answer(reply) == vlm.VlmAnswer(answer="Hi.", confident=True)


@pytest.mark.parametrize("reply", ["", "Hi there", '{"answer": "Hi."}'])
def test_parse_answer_rejects_unusable_replies(reply: str) -> None:
    with pytest.raises(vlm.VlmError):
        vlm.parse_answer(reply)
