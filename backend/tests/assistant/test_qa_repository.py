"""qa_log tests (B11) against a real throw-away database `va_test_qa`.

Needs Postgres (docker compose up -d); skipped locally without it, required in CI.
"""

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from app.assistant import qa_repository
from app.config import settings
from app.contracts import Evidence

TEST_DB = "va_test_qa"
REAL_CONNECT = qa_repository._connect  # captured before tests/conftest.py replaces it


@pytest.fixture(scope="module")
def qa_db_url() -> Iterator[str]:
    try:
        admin = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as exc:
        if os.environ.get("REQUIRE_DB") == "1":
            raise
        pytest.skip(f"Postgres is not running (docker compose up -d): {exc}")
    with admin:
        admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {TEST_DB}")
    yield make_conninfo(settings.database_url, dbname=TEST_DB)


@pytest.fixture
def qa_db(qa_db_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Empty qa_log in the test database (the table is created by the repository itself)."""
    monkeypatch.setattr(qa_repository, "_connect", REAL_CONNECT)
    monkeypatch.setattr(qa_repository, "database_url", lambda: qa_db_url)
    monkeypatch.setattr(qa_repository, "_schema_ready", False)
    monkeypatch.setattr(qa_repository, "_down_until", 0.0)
    with psycopg.connect(qa_db_url, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS qa_log")
    return qa_db_url


EVIDENCE = [
    Evidence(frame_id=7, captured_at=datetime(2026, 11, 4, 12, 0, tzinfo=UTC),
             thumb_url="/media/thumbs/7.jpg", score=0.9),
]


def test_save_creates_the_table_and_returns_the_record(qa_db: str) -> None:
    record = qa_repository.save(
        "What does the sign say?", "en", "The sign says exit.", True, EVIDENCE,
        {"stt": 900, "search": 3, "vlm": 800, "total": 1710},
    )
    assert record is not None
    assert record.id == 1
    assert record.asked_at.tzinfo is not None
    assert record.evidence == EVIDENCE
    assert record.timings_ms["total"] == 1710


def test_list_is_newest_first_and_limited(qa_db: str) -> None:
    for i in range(3):
        qa_repository.save(f"question {i}", "fr", f"answer {i}", False, [], {})
    records = qa_repository.list_recent(limit=2)
    assert [r.question for r in records] == ["question 2", "question 1"]
    assert records[0].language == "fr"
    assert qa_repository.last_asked_at() == records[0].asked_at


def test_arabic_text_round_trips(qa_db: str) -> None:
    qa_repository.save("ماذا يوجد أمامي؟", "ar", "يوجد باب أمامك.", True, [], {})
    assert qa_repository.list_recent()[0].answer == "يوجد باب أمامك."


def test_database_down_is_harmless_and_not_retried_at_once(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(qa_repository, "_connect", REAL_CONNECT)
    monkeypatch.setattr(qa_repository, "database_url", lambda: "postgresql://va:va@127.0.0.1:1/x")
    monkeypatch.setattr(qa_repository, "_down_until", 0.0)

    assert qa_repository.save("q", "en", "a", True, [], {}) is None  # one real attempt
    started = time.perf_counter()
    assert qa_repository.save("q", "en", "a", True, [], {}) is None  # no second attempt
    assert qa_repository.list_recent() == []
    assert qa_repository.last_asked_at() is None
    assert time.perf_counter() - started < 0.5, "while marked down, answers are not delayed"
