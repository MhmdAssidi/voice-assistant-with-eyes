"""Live status and history events tests (B11)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import status as status_api
from app.assistant import answer, qa_repository, vlm
from app.contracts import Event, FrameDetail
from app.main import app
from app.memory import search
from app.realtime.hub import hub

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("last_ingest_status", "last_ingest_at", "last_frame_at", "last_question_at"):
        monkeypatch.setattr(hub, name, None)


def ingest_event(connected: bool = True) -> dict:
    return {
        "type": "ingest_status",
        "ts": datetime.now(UTC).isoformat(),
        "data": {"stream_connected": connected, "ingest_running": True,
                 "frames_seen": 120, "frames_kept": 9, "avg_process_ms": 85},
    }


def test_status_reflects_a_fresh_ingest_status() -> None:
    assert client.post("/api/internal/events", json=ingest_event()).status_code == 200
    s = client.get("/api/status").json()
    assert (s["stream_connected"], s["ingest_running"]) == (True, True)
    assert (s["frames_seen"], s["frames_kept"], s["avg_process_ms"]) == (120, 9, 85)


def test_status_goes_down_when_the_worker_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    client.post("/api/internal/events", json=ingest_event())
    # The worker posts every 2 s; pretend the last post was 6 s ago.
    hub.last_ingest_at = datetime.now(UTC) - timedelta(seconds=status_api.STALE_AFTER_S + 1)
    s = client.get("/api/status").json()
    assert (s["stream_connected"], s["ingest_running"]) == (False, False)
    assert s["frames_seen"] == 120, "last known counters are still shown"


def test_status_shows_the_last_frame_and_question_times() -> None:
    frame_time = "2026-11-04T10:00:00+00:00"
    client.post("/api/internal/events", json={
        "type": "frame_stored", "ts": frame_time,
        "data": {"id": 5, "captured_at": frame_time, "thumb_url": "", "ocr_text": "",
                 "object_labels": [], "enhanced": False},
    })
    s = client.get("/api/status").json()
    assert s["last_frame_at"].startswith("2026-11-04T10:00:00")


class FakeProvider:
    name = "fake"

    def generate(self, system: str, user: str, images: list[bytes]) -> vlm.VlmAnswer:
        return vlm.VlmAnswer(answer="There is a door in front of you.", confident=True)


def test_a_new_answer_is_pushed_to_the_dashboard_instantly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(answer, "get_provider", lambda: FakeProvider())
    # A8: search reads the real database now (empty in tests), so give it a frame "in front"
    in_front = FrameDetail(id=1, captured_at=datetime.now(UTC), thumb_url="", ocr_text="",
                           object_labels=["door"], enhanced=False, image_url="", width=640,
                           height=480, sharpness=150.0, brightness=120.0, ocr_blocks=[], objects=[])
    monkeypatch.setattr(search, "get_latest_frame", lambda max_age_s=10: in_front)
    with client.websocket_connect("/ws/events") as ws:
        r = client.post("/api/ask", data={"text": "What is in front of me?", "lang_hint": "en"})
        assert r.status_code == 200
        event = Event.model_validate_json(ws.receive_text())

    assert event.type == "question_answered"
    assert event.data["question"] == "What is in front of me?"
    assert event.data["answer"] == "There is a door in front of you."
    assert "asked_at" in event.data and "timings_ms" in event.data
    # database is down in tests (see tests/conftest.py): id 0, answer still delivered
    assert r.json()["id"] == 0
    assert client.get("/api/status").json()["last_question_at"] is not None


def test_ask_uses_the_saved_record_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(answer, "get_provider", lambda: FakeProvider())
    saved = {}

    def fake_save(question, language, text, confident, evidence, timings):  # noqa: ANN001, ANN202
        from app.contracts import QaRecord

        saved["question"] = question
        return QaRecord(id=42, asked_at=datetime.now(UTC), question=question, language=language,
                        answer=text, confident=confident, evidence=evidence, timings_ms=timings)

    monkeypatch.setattr(qa_repository, "save", fake_save)
    r = client.post("/api/ask", data={"text": "Que dit le panneau ?", "lang_hint": "fr"})
    assert r.json()["id"] == 42
    assert saved["question"] == "Que dit le panneau ?"
