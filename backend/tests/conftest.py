"""Fixtures for all backend tests (SHARED file).

Student B: tests must never use the real database for Q&A history, nor call the
real vision-language model (slow, needs the internet, spends the free quota).
These defaults are overridden by the tests that need something else:
- tests/assistant/test_qa_repository.py uses a real throw-away database;
- tests that check answers install their own fake model.
"""

import psycopg
import pytest

from app.assistant import answer, live_view, qa_repository, vlm


def _no_database() -> psycopg.Connection:
    raise psycopg.OperationalError("no database in tests")


class _NoModel:
    name = "none"

    def generate(self, system: str, user: str, images: list[bytes]) -> vlm.VlmAnswer:
        raise vlm.VlmError("no real model in tests")


@pytest.fixture(autouse=True)
def _isolated_from_real_services(monkeypatch: pytest.MonkeyPatch) -> None:
    # Q&A history: behaves like "Postgres is down" (the designed fallback: answer still works)
    monkeypatch.setattr(qa_repository, "_connect", _no_database)
    # Vision-language model: behaves like "model unavailable" (spoken apology)
    monkeypatch.setattr(answer, "get_provider", lambda: _NoModel())
    # Live camera snapshot: behaves like "no stream right now" (stored frames are used)
    monkeypatch.setattr(live_view, "grab", lambda: None)
