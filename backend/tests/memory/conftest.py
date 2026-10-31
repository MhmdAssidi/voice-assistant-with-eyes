"""Database fixture for memory tests (owner: Student A).

Creates a throw-away database `va_test` next to the real one, loads
db/init/001_frames.sql into it and points the pool at it, so tests never touch
real frames. Needs Postgres running (docker compose up -d); without it the
tests are skipped locally, but they fail in CI where REQUIRE_DB=1.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from app import db
from app.config import BACKEND_DIR, settings

TEST_DB = "va_test"
SCHEMA_FILE = BACKEND_DIR / "db" / "init" / "001_frames.sql"


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    try:
        admin = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as exc:
        if os.environ.get("REQUIRE_DB") == "1":
            raise
        pytest.skip(f"Postgres is not running (docker compose up -d): {exc}")

    with admin:
        admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {TEST_DB}")
    url = make_conninfo(settings.database_url, dbname=TEST_DB)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(Path(SCHEMA_FILE).read_text(encoding="utf-8"))

    db.open_pool(url)
    yield url
    db.close_pool()


@pytest.fixture
def clean_frames(test_db_url: str) -> None:
    """Start each test with an empty frames table."""
    with db.get_conn() as conn:
        conn.execute("TRUNCATE frames RESTART IDENTITY")
