"""A8 tests: search by time and meaning, and the frames/search REST API.

The CLIP text model is replaced by a fake that returns hand-made vectors with KNOWN
cosine similarities (in the ranges the real model gives, see search.py), so these
run fast in CI but still go through the real SQL (HNSW, GIN, time window) on va_test.
Run from backend/:  pytest tests/memory/test_search.py -v
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.contracts import FrameDetail, FrameSummary, SearchHit
from app.main import app
from app.memory import files, search
from app.memory import repository as repo
from app.memory.embeddings import DIM

THRESHOLD = settings.confidence_threshold  # Student B: below this -> "I'm not sure"


def unit(i: int) -> np.ndarray:
    return np.eye(DIM, dtype=np.float32)[i]


def vec(similarities: dict[int, float]) -> np.ndarray:
    """A unit vector whose cosine with unit(i) is exactly similarities[i]."""
    v = np.zeros(DIM, dtype=np.float32)
    for i, s in similarities.items():
        v[i] = s
    assert float(v @ v) <= 1.0, "impossible: squared similarities must add up to <= 1"
    v[DIM - 1] = np.sqrt(max(0.0, 1.0 - float(v @ v)))  # the rest points elsewhere
    return v


# Each stored frame has image_emb = unit(a) and text_emb = unit(b).
EXIT_IMG, EXIT_TXT = 0, 1
ROOM_IMG, ROOM_TXT = 2, 3
SORTIE_IMG, SORTIE_TXT = 4, 5
ARABIC_IMG, ARABIC_TXT = 6, 7

QUESTIONS = {
    # a real exit-sign question: picture 0.30, caption 0.90 (+ the word "exit" was read)
    # (the room picture is a little similar too: it shows up second, with a low score)
    "What did the exit sign say?": vec({EXIT_IMG: 0.30, EXIT_TXT: 0.90, ROOM_IMG: 0.25}),
    "a chair and a tv": vec({ROOM_IMG: 0.27, ROOM_TXT: 0.86}),
    # meaning matches nothing well: only the word read on the sign can find it
    "sortie": vec({SORTIE_IMG: 0.22, SORTIE_TXT: 0.80}),
    "المخرج": vec({}),
    # unrelated: everything below the calibrated ranges
    "a plate of spaghetti": vec({EXIT_IMG: 0.17, ROOM_IMG: 0.19, EXIT_TXT: 0.70, ROOM_TXT: 0.62}),
}


class FakeTextEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed_text(self, text: str) -> np.ndarray:
        self.calls += 1
        return QUESTIONS[text]


@pytest.fixture
def embedder(monkeypatch) -> FakeTextEmbedder:
    fake = FakeTextEmbedder()
    monkeypatch.setattr(search, "get_text_embedder", lambda: fake)
    return fake


def store(seconds_ago: float, ocr: str = "", image: int = 10, text: int | None = 11,
          now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return repo.insert_frame(repo.NewFrame(
        captured_at=now - timedelta(seconds=seconds_ago),
        image_path="frames/x.jpg", thumb_path="thumbs/x.jpg", width=640, height=480,
        sharpness=150.0, brightness=120.0, ocr_text=ocr,
        image_emb=unit(image), text_emb=None if text is None else unit(text),
    ))


@pytest.fixture
def walk(clean_frames, embedder) -> dict[str, int]:
    """Four scenes seen during a short walk."""
    return {
        "exit": store(60, "EXIT\nRoom 204", EXIT_IMG, EXIT_TXT),
        "room": store(30, "", ROOM_IMG, ROOM_TXT),
        "sortie": store(120, "SORTIE", SORTIE_IMG, SORTIE_TXT),
        "arabic": store(90, "مخرج", ARABIC_IMG, ARABIC_TXT),
    }


# ---------- pure helpers ----------

def test_question_words_for_ocr() -> None:
    assert search.query_terms("What did the EXIT sign say?") == [["exit"]]
    assert search.query_terms("Qu'est-ce qui était écrit sur le panneau sortie ?") == [["sortie"]]
    assert search.query_terms("sécurité") == [["sécurité", "securite"]]
    assert search.query_terms("شو كان مكتوب على المخرج") == [["المخرج", "مخرج"]]
    assert search.query_terms("room 204") == [["room"], ["204"]]


def test_score_formula() -> None:
    # perfect content, captured right now -> 1.0
    assert search.score_frame(0.31, 0.97, 1, 1, age_s=0).total == pytest.approx(1.0)
    # same frame 10 min old: recency exp(-1)
    parts = search.score_frame(0.31, 0.97, 1, 1, age_s=600)
    assert parts.recency == pytest.approx(np.exp(-1))
    assert parts.total == pytest.approx(0.85 + 0.15 * np.exp(-1))
    # half the question words read on the sign
    assert search.score_frame(None, None, 1, 2, age_s=0).ocr == 0.75
    # nothing matches: content 0, only recency
    assert search.score_frame(0.10, 0.50, 0, 1, age_s=0).content == 0


# ---------- search_frames on the database ----------

def test_exit_sign_question_finds_the_exit_frame_first(walk) -> None:
    hits = search.search_frames("What did the exit sign say?")
    assert hits[0].frame.id == walk["exit"]
    assert hits[0].score >= THRESHOLD
    assert hits[0].matched_by == ["image", "text", "ocr"]
    assert hits[0].frame.ocr_text == "EXIT\nRoom 204"
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_a_word_read_on_the_sign_is_enough(walk) -> None:
    hits = search.search_frames("sortie")
    assert hits[0].frame.id == walk["sortie"]
    assert "ocr" in hits[0].matched_by and hits[0].score >= THRESHOLD

    hits = search.search_frames("المخرج")  # "the exit": Arabic article removed
    assert [h.frame.id for h in hits] == [walk["arabic"]]
    assert hits[0].matched_by == ["ocr"]


def test_objects_question_finds_the_room(walk) -> None:
    hits = search.search_frames("a chair and a tv")
    assert hits[0].frame.id == walk["room"]
    assert hits[0].score >= THRESHOLD


def test_unrelated_question_finds_nothing(walk) -> None:
    assert search.search_frames("a plate of spaghetti") == []


def test_time_window(walk) -> None:
    now = datetime.now(UTC)
    recent = search.search_frames("What did the exit sign say?", since=now - timedelta(seconds=45))
    assert walk["exit"] not in [h.frame.id for h in recent]  # seen 60 s ago

    older = search.search_frames("What did the exit sign say?",
                                 since=now - timedelta(minutes=10),
                                 until=now - timedelta(seconds=50))
    assert older[0].frame.id == walk["exit"]
    assert "time" in older[0].matched_by
    assert walk["room"] not in [h.frame.id for h in older]  # seen 30 s ago, after `until`


def test_newer_frame_wins_a_tie(clean_frames, embedder) -> None:
    old = store(500, "EXIT", EXIT_IMG, EXIT_TXT)
    new = store(20, "EXIT", EXIT_IMG, EXIT_TXT)
    hits = search.search_frames("What did the exit sign say?", limit=1)
    assert [h.frame.id for h in hits] == [new]
    assert old != new


def test_limit_and_contract_shape(walk) -> None:
    hits = search.search_frames("What did the exit sign say?", limit=2)
    assert len(hits) == 2
    for hit in hits:
        SearchHit.model_validate(hit.model_dump())
        assert 0.0 <= hit.score <= 1.0
        assert hit.frame.thumb_url == "/media/thumbs/x.jpg"


def test_empty_window_does_not_load_the_model(clean_frames, monkeypatch) -> None:
    def no_model():
        raise AssertionError("the text model must not load when there is nothing to search")

    monkeypatch.setattr(search, "get_text_embedder", no_model)
    assert search.search_frames("anything") == []
    store(3600)  # an hour ago, outside the window
    assert search.search_frames("anything", since=datetime.now(UTC) - timedelta(minutes=10)) == []


# ---------- the other contract functions ----------

def test_latest_frame_only_when_recent(clean_frames) -> None:
    store(30, "old")
    assert search.get_latest_frame(max_age_s=10) is None
    new = store(2, "EXIT")
    latest = search.get_latest_frame(max_age_s=10)
    assert isinstance(latest, FrameDetail)
    assert (latest.id, latest.ocr_text, latest.image_url) == (new, "EXIT", "/media/frames/x.jpg")


def test_frame_image_path_and_count(clean_frames) -> None:
    frame_id = store(5)
    assert search.get_frame_image_path(frame_id) == str(files.absolute("frames/x.jpg"))
    assert search.get_frame_image_path(999) == str(files.absolute("frames/999.jpg"))
    assert search.count_frames() == 1


def test_database_down_is_not_an_error(clean_frames, embedder, monkeypatch) -> None:
    """Student B's /api/ask must still answer ("nothing stored") when Postgres is down."""
    def database_down():
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(search, "get_conn", database_down)
    monkeypatch.setattr(repo, "get_conn", database_down)
    assert search.search_frames("sortie") == []
    assert search.get_latest_frame() is None
    assert search.count_frames() == 0
    assert search.get_frame_image_path(7).endswith("7.jpg")

    client = TestClient(app)
    assert client.get("/api/frames").status_code == 503
    assert client.get("/api/search", params={"q": "sortie"}).status_code == 503


# ---------- REST API ----------

def test_frames_api_newest_first_with_paging(clean_frames) -> None:
    client = TestClient(app)
    ids = [store(seconds_ago) for seconds_ago in (40, 30, 20, 10)]  # ids in time order

    page1 = [FrameSummary(**f) for f in client.get("/api/frames", params={"limit": 3}).json()]
    assert [f.id for f in page1] == ids[::-1][:3]
    page2 = client.get("/api/frames", params={"limit": 3, "before_id": page1[-1].id}).json()
    assert [f["id"] for f in page2] == [ids[0]]

    detail = FrameDetail(**client.get(f"/api/frames/{ids[0]}").json())
    assert (detail.width, detail.height) == (640, 480)
    assert client.get("/api/frames/999999").status_code == 404
    assert client.get("/api/frames", params={"limit": 500}).status_code == 422


def test_search_api(walk) -> None:
    client = TestClient(app)
    r = client.get("/api/search", params={"q": "sortie"})
    assert r.status_code == 200
    hits = [SearchHit(**h) for h in r.json()]
    assert hits[0].frame.id == walk["sortie"]
    assert client.get("/api/search").status_code == 422  # q is required
