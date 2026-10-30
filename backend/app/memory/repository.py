"""Frames table access (owner: Student A, task A1).

The only module that writes SQL for the `frames` table. The ingest pipeline (A7)
inserts frames, search (A8) and the REST API read them, retention (A9) deletes them.

Image paths are stored relative to FRAMES_DIR ("frames/12.jpg", "thumbs/12.jpg"),
and FRAMES_DIR is served at /media, so the URL is simply "/media/" + path.
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.contracts import DetectedObject, FrameDetail, FrameSummary, OcrBlock
from app.db import get_conn

MAX_LIST_LIMIT = 200  # contract: GET /api/frames limit max 200

# Every column except the two 512-dim embeddings and the tsvector (heavy, rarely needed)
_COLUMNS = """id, captured_at, image_path, thumb_path, width, height, sharpness, brightness,
    enhanced, dhash, ocr_text, ocr_blocks, objects, caption_text"""


def _to_signed64(value: int | None) -> int | None:
    """A dHash is an unsigned 64-bit number; Postgres BIGINT is signed."""
    if value is None:
        return None
    return value - (1 << 64) if value >= (1 << 63) else value


def _to_unsigned64(value: int | None) -> int | None:
    if value is None:
        return None
    return value + (1 << 64) if value < 0 else value


@dataclass
class NewFrame:
    """Everything the ingest pipeline knows about a frame before it is stored."""

    captured_at: datetime
    image_path: str
    thumb_path: str
    width: int
    height: int
    sharpness: float
    brightness: float
    enhanced: bool = False
    dhash: int | None = None
    ocr_text: str = ""
    ocr_blocks: list[OcrBlock] = field(default_factory=list)
    objects: list[DetectedObject] = field(default_factory=list)
    caption_text: str = ""
    image_emb: np.ndarray | None = None
    text_emb: np.ndarray | None = None
    id: int | None = None  # set it from reserve_frame_id() to name files by id


@dataclass
class FrameRow:
    """One row of the frames table, as read back from the database."""

    id: int
    captured_at: datetime
    image_path: str
    thumb_path: str
    width: int
    height: int
    sharpness: float
    brightness: float
    enhanced: bool
    dhash: int | None
    ocr_text: str
    ocr_blocks: list[OcrBlock]
    objects: list[DetectedObject]
    caption_text: str
    image_emb: np.ndarray | None = None  # only filled when asked for
    text_emb: np.ndarray | None = None

    @property
    def thumb_url(self) -> str:
        return f"/media/{self.thumb_path}"

    @property
    def image_url(self) -> str:
        return f"/media/{self.image_path}"

    @property
    def object_labels(self) -> list[str]:
        """Unique labels in detection order, e.g. ["person", "chair"]."""
        return list(dict.fromkeys(obj.label for obj in self.objects))

    def to_summary(self) -> FrameSummary:
        return FrameSummary(
            id=self.id,
            captured_at=self.captured_at,
            thumb_url=self.thumb_url,
            ocr_text=self.ocr_text,
            object_labels=self.object_labels,
            enhanced=self.enhanced,
        )

    def to_detail(self) -> FrameDetail:
        return FrameDetail(
            **self.to_summary().model_dump(),
            image_url=self.image_url,
            width=self.width,
            height=self.height,
            sharpness=self.sharpness,
            brightness=self.brightness,
            ocr_blocks=self.ocr_blocks,
            objects=self.objects,
        )


@dataclass
class DeletedFrame:
    """What retention needs to remove a deleted row's files from disk."""

    id: int
    image_path: str
    thumb_path: str


def _as_numpy(vector) -> np.ndarray | None:
    """pgvector >= 0.4 reads `vector` columns as its own Vector type; we use numpy."""
    if vector is None or isinstance(vector, np.ndarray):
        return vector
    return vector.to_numpy()


def _row_to_frame(row: dict) -> FrameRow:
    return FrameRow(
        id=row["id"],
        captured_at=row["captured_at"],
        image_path=row["image_path"],
        thumb_path=row["thumb_path"],
        width=row["width"] or 0,
        height=row["height"] or 0,
        sharpness=row["sharpness"] or 0.0,
        brightness=row["brightness"] or 0.0,
        enhanced=bool(row["enhanced"]),
        dhash=_to_unsigned64(row["dhash"]),
        ocr_text=row["ocr_text"] or "",
        ocr_blocks=[OcrBlock(**b) for b in row["ocr_blocks"] or []],
        objects=[DetectedObject(**o) for o in row["objects"] or []],
        caption_text=row["caption_text"] or "",
        image_emb=_as_numpy(row.get("image_emb")),
        text_emb=_as_numpy(row.get("text_emb")),
    )


def reserve_frame_id() -> int:
    """Take the next id before inserting, so the JPEG can be named <id>.jpg first."""
    with get_conn() as conn:
        return conn.execute("SELECT nextval(pg_get_serial_sequence('frames', 'id'))").fetchone()[0]


def insert_frame(frame: NewFrame) -> int:
    """Store one frame and return its id."""
    values = {
        "captured_at": frame.captured_at,
        "image_path": frame.image_path,
        "thumb_path": frame.thumb_path,
        "width": frame.width,
        "height": frame.height,
        "sharpness": frame.sharpness,
        "brightness": frame.brightness,
        "enhanced": frame.enhanced,
        "dhash": _to_signed64(frame.dhash),
        "ocr_text": frame.ocr_text,
        "ocr_blocks": Jsonb([b.model_dump() for b in frame.ocr_blocks]),
        "objects": Jsonb([o.model_dump() for o in frame.objects]),
        "caption_text": frame.caption_text,
        "image_emb": frame.image_emb,
        "text_emb": frame.text_emb,
    }
    if frame.id is not None:
        values["id"] = frame.id
    columns = ", ".join(values)
    placeholders = ", ".join(f"%({name})s" for name in values)
    with get_conn() as conn:
        row = conn.execute(
            f"INSERT INTO frames ({columns}) VALUES ({placeholders}) RETURNING id", values
        ).fetchone()
    return row[0]


def get_frame(frame_id: int, with_embeddings: bool = False) -> FrameRow | None:
    """One frame by id, or None if it does not exist (or was deleted by retention)."""
    columns = _COLUMNS + (", image_emb, text_emb" if with_embeddings else "")
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(f"SELECT {columns} FROM frames WHERE id = %s", (frame_id,)).fetchone()
    return _row_to_frame(row) if row else None


def list_frames(
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    before_id: int | None = None,
) -> list[FrameRow]:
    """Frames newest first. `before_id` gives the next page for infinite scroll."""
    conditions = ["TRUE"]
    params: dict = {"limit": max(1, min(limit, MAX_LIST_LIMIT))}
    if since is not None:
        conditions.append("captured_at >= %(since)s")
        params["since"] = since
    if until is not None:
        conditions.append("captured_at <= %(until)s")
        params["until"] = until
    if before_id is not None:
        conditions.append("id < %(before_id)s")
        params["before_id"] = before_id
    sql = (
        f"SELECT {_COLUMNS} FROM frames WHERE {' AND '.join(conditions)} "
        "ORDER BY captured_at DESC, id DESC LIMIT %(limit)s"
    )
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return [_row_to_frame(r) for r in rows]


def count_frames() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT count(*) FROM frames").fetchone()[0]


def oldest_frame_at() -> datetime | None:
    """Capture time of the oldest stored frame (None if the table is empty)."""
    with get_conn() as conn:
        return conn.execute("SELECT min(captured_at) FROM frames").fetchone()[0]


def delete_frames_older_than(cutoff: datetime) -> list[DeletedFrame]:
    """Delete rows captured before `cutoff`; return them so their files can be removed."""
    with get_conn() as conn:
        rows = conn.execute(
            "DELETE FROM frames WHERE captured_at < %s RETURNING id, image_path, thumb_path",
            (cutoff,),
        ).fetchall()
    return [DeletedFrame(id=r[0], image_path=r[1], thumb_path=r[2]) for r in rows]
