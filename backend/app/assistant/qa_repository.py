"""The qa_log table: every question and its answer (owner: Student B, task B11).

Reliability first: if Postgres is down, saving or listing logs a warning and
returns nothing, but the phone still gets its answer. That is also why we open
a short-lived connection with a 2-second timeout instead of using the shared
pool, whose 10-second wait would delay every answer while the database is down.
"""

import logging
import time
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import BACKEND_DIR, settings
from app.contracts import Evidence, QaRecord

log = logging.getLogger("uvicorn.error")

SCHEMA_FILE = BACKEND_DIR / "db" / "init" / "002_qa.sql"
CONNECT_TIMEOUT_S = 2
RETRY_AFTER_S = 30  # after a failure, don't try again for a while (answers stay fast)

_schema_ready = False
_down_until = 0.0  # time.monotonic() before which we don't even try


def database_url() -> str:
    return settings.database_url  # tests point this at a throw-away database


def _connect() -> psycopg.Connection:
    global _down_until
    if time.monotonic() < _down_until:
        raise psycopg.OperationalError("database marked down, retrying later")
    try:
        conn = psycopg.connect(
            database_url(), connect_timeout=CONNECT_TIMEOUT_S, row_factory=dict_row
        )
    except psycopg.OperationalError:
        # On Windows even a refused connection takes ~2 s: don't pay that on every answer.
        _down_until = time.monotonic() + RETRY_AFTER_S
        raise
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: psycopg.Connection) -> None:
    """Creates qa_log if missing (once per process; the SQL is idempotent)."""
    global _schema_ready
    if not _schema_ready:
        conn.execute(Path(SCHEMA_FILE).read_text(encoding="utf-8"))
        conn.commit()
        _schema_ready = True


def save(
    question: str,
    language: str,
    answer: str,
    confident: bool,
    evidence: list[Evidence],
    timings_ms: dict[str, int],
) -> QaRecord | None:
    """Stores one Q&A; returns it with its id and time, or None if the database is down."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """INSERT INTO qa_log (question, language, answer, confident, evidence, timings_ms)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                (
                    question,
                    language,
                    answer,
                    confident,
                    Jsonb([e.model_dump(mode="json") for e in evidence]),
                    Jsonb(timings_ms),
                ),
            ).fetchone()
    except psycopg.Error as error:
        log.warning("qa_log: could not save the question: %s", error)
        return None
    return _record(row)


def list_recent(limit: int = 50) -> list[QaRecord]:
    """Newest first."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_log ORDER BY asked_at DESC, id DESC LIMIT %s", (limit,)
            ).fetchall()
    except psycopg.Error as error:
        log.warning("qa_log: could not list questions: %s", error)
        return []
    return [_record(row) for row in rows]


def last_asked_at() -> datetime | None:
    try:
        with _connect() as conn:
            row = conn.execute("SELECT max(asked_at) AS last FROM qa_log").fetchone()
    except psycopg.Error as error:
        log.warning("qa_log: could not read the last question time: %s", error)
        return None
    return row["last"] if row else None


def _record(row: dict) -> QaRecord:
    return QaRecord(
        id=row["id"],
        asked_at=row["asked_at"],
        question=row["question"],
        language=row["language"],
        answer=row["answer"],
        confident=row["confident"],
        evidence=row["evidence"] or [],
        timings_ms=row["timings_ms"] or {},
    )
