"""PostgreSQL connection pool (owner: Student A, task A1).

One small pool per process (API or ingest worker). It opens lazily on first use,
so importing the app never needs a running database. Every connection has the
pgvector types registered, so `vector` columns read and write as numpy arrays.

Usage:
    from app.db import get_conn
    with get_conn() as conn:
        conn.execute("SELECT 1")
The `with` block commits on success and rolls back on error.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None


def _configure(conn: psycopg.Connection) -> None:
    """Called once for each new connection in the pool."""
    register_vector(conn)


def open_pool(url: str | None = None) -> ConnectionPool:
    """Open the pool (tests pass their own database URL). Replaces any open pool."""
    global _pool
    close_pool()
    _pool = ConnectionPool(
        conninfo=url or settings.database_url,
        min_size=1,
        max_size=5,
        configure=_configure,
        timeout=10,  # seconds to wait for a free connection before raising
        open=True,
    )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Borrow a connection from the pool (opened on first call)."""
    pool = _pool or open_pool()
    with pool.connection() as conn:
        yield conn
