"""S0 smoke tests: every contract endpoint answers with the agreed shape.

Run from backend/:  pytest
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.contracts import AskResponse, FrameDetail, FrameSummary, QaRecord, SearchHit, SystemStatus
from app.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_frames_list_and_detail() -> None:
    r = client.get("/api/frames")
    assert r.status_code == 200
    frames = [FrameSummary(**f) for f in r.json()]
    assert len(frames) > 0
    # newest first
    assert frames[0].captured_at >= frames[-1].captured_at

    r = client.get(f"/api/frames/{frames[0].id}")
    assert r.status_code == 200
    FrameDetail(**r.json())

    assert client.get("/api/frames/999999").status_code == 404


def test_search() -> None:
    r = client.get("/api/search", params={"q": "exit sign"})
    assert r.status_code == 200
    hits = [SearchHit(**h) for h in r.json()]
    assert all(0.0 <= h.score <= 1.0 for h in hits)


def test_ask_with_text() -> None:
    r = client.post("/api/ask", data={"text": "What's in front of me?", "lang_hint": "fr"})
    assert r.status_code == 200
    answer = AskResponse(**r.json())
    assert answer.language == "fr"
    assert "safe" not in answer.answer.lower()


def test_ask_with_audio() -> None:
    files = {"audio": ("question.m4a", b"fake-audio-bytes", "audio/mp4")}
    r = client.post("/api/ask", files=files)
    assert r.status_code == 200
    AskResponse(**r.json())


def test_ask_needs_audio_or_text() -> None:
    assert client.post("/api/ask").status_code == 422


def test_questions_and_status() -> None:
    r = client.get("/api/questions")
    assert r.status_code == 200
    [QaRecord(**q) for q in r.json()]

    r = client.get("/api/status")
    assert r.status_code == 200
    SystemStatus(**r.json())


def test_event_reaches_websocket_and_status() -> None:
    event = {
        "type": "ingest_status",
        "ts": datetime.now(UTC).isoformat(),
        "data": {
            "stream_connected": True,
            "ingest_running": True,
            "frames_seen": 42,
            "frames_kept": 7,
            "avg_process_ms": 120,
        },
    }
    with client.websocket_connect("/ws/events") as ws:
        r = client.post("/api/internal/events", json=event)
        assert r.json() == {"ok": True}
        received = ws.receive_json()
        assert received["type"] == "ingest_status"

    status = client.get("/api/status").json()
    assert status["frames_seen"] == 42
    assert status["stream_connected"] is True
