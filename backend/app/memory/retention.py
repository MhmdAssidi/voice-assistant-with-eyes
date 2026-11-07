"""Retention: forget old frames automatically (owner: Student A, task A9).

Privacy rule of the project: the assistant only needs a SHORT memory ("what did that
sign say?"), so frames older than RETENTION_MINUTES (default 30) are deleted: the
database row AND both JPEG files. Student B's Q&A history is kept (qa_log has no
foreign key to frames); its evidence thumbnails simply disappear.

The ingest worker runs this when it starts and then every RETENTION_CHECK_S (60 s).
Run it by hand (e.g. after tests or a demo):
    python -m app.memory.retention              # delete what is too old
    python -m app.memory.retention --minutes 0  # delete EVERY frame
"""

import argparse
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.db import DB_ERRORS, get_conn
from app.memory import files
from app.memory import repository as repo

log = logging.getLogger(__name__)

ORPHAN_MIN_AGE_S = 120  # a file written seconds ago may be waiting for its row: leave it


@dataclass
class PurgeResult:
    frames: int  # rows deleted (each with its 2 files)
    orphan_files: int  # files on disk that had no row any more


def purge_old_frames(now: datetime | None = None, minutes: float | None = None) -> int:
    """Delete frames captured more than `minutes` ago, rows then files; return how many."""
    now = now or datetime.now(UTC)
    keep_minutes = settings.retention_minutes if minutes is None else minutes
    deleted = repo.delete_frames_older_than(now - timedelta(minutes=keep_minutes))
    for frame in deleted:
        files.delete_files(frame.image_path, frame.thumb_path)
    return len(deleted)


def remove_orphan_files(min_age_s: float = ORPHAN_MIN_AGE_S) -> int:
    """Delete frame files whose row is gone (e.g. the process was killed mid-way)."""
    candidates: dict[int, list] = {}
    cutoff = time.time() - min_age_s
    for folder in ("frames", "thumbs"):
        for path in files.absolute(folder).glob("*.jpg"):
            if path.stem.isdigit() and path.stat().st_mtime < cutoff:
                candidates.setdefault(int(path.stem), []).append(path)
    if not candidates:
        return 0
    with get_conn() as conn:
        existing = {row[0] for row in conn.execute(
            "SELECT id FROM frames WHERE id = ANY(%s)", (list(candidates),)
        )}
    removed = 0
    for frame_id, paths in candidates.items():
        if frame_id not in existing:
            for path in paths:
                path.unlink(missing_ok=True)
                removed += 1
    return removed


def run_once(minutes: float | None = None) -> PurgeResult:
    result = PurgeResult(purge_old_frames(minutes=minutes), remove_orphan_files())
    if result.frames or result.orphan_files:
        log.info("Retention: deleted %d frame(s) older than %s min and %d orphan file(s)",
                 result.frames, settings.retention_minutes if minutes is None else minutes,
                 result.orphan_files)
    return result


class RetentionJob:
    """Background thread: run_once() now, then every `interval_s` until stop()."""

    def __init__(self, interval_s: float | None = None) -> None:
        self.interval_s = settings.retention_check_s if interval_s is None else interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="retention", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while True:
            try:
                run_once()
            except DB_ERRORS as error:  # database restarting: try again next time
                log.warning("Retention skipped, database unavailable: %s", error)
            except Exception:  # never let a cleanup problem stop the worker
                log.exception("Retention failed")
            if self._stop.wait(self.interval_s):
                return


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete old frames (rows and files)")
    parser.add_argument("--minutes", type=float, default=None,
                        help=f"keep this many minutes (default RETENTION_MINUTES="
                             f"{settings.retention_minutes}); 0 deletes everything")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    before = repo.count_frames()
    result = run_once(args.minutes)
    print(f"Deleted {result.frames} of {before} frame(s) and {result.orphan_files} orphan "
          f"file(s); {repo.count_frames()} frame(s) left.")


if __name__ == "__main__":
    main()
