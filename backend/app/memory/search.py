"""Frame search: find stored frames by time and by meaning (owner: Student A, task A8).

The four public functions are the contract Student B's /api/ask relies on; their
signatures must not change:
    search_frames(query, since, until, limit) -> list[SearchHit]
    get_latest_frame(max_age_s)               -> FrameDetail | None
    get_frame_image_path(frame_id)            -> str
    count_frames()                            -> int
They never raise on a database problem (Postgres down, ...): they log it and return
"nothing", so a question still gets a spoken answer instead of an error.

How search_frames ranks frames (hybrid search, all inside the time window):
1. The question is embedded with the multilingual CLIP text model (en/fr/ar).
2. Candidates come from three indexes:
     HNSW on image_emb  (question vs the picture itself, cosine)
     HNSW on text_emb   (question vs the frame caption, cosine)
     GIN on ocr_tsv     (question words that were literally read on a sign)
3. Each candidate gets a score in 0..1:
     image, text = CLIP cosine rescaled to 0..1 (calibrated ranges below)
     ocr         = 0 if no question word was read, else 0.5 + 0.5 * share of words read
     content     = 0.5 * image + 0.3 * text + 0.2 * ocr
     recency     = exp(-age_s / 600)              ("that sign" usually means a recent one)
     score       = 0.85 * content + 0.15 * recency
A correct match scores >= 0.25 (Student B's CONFIDENCE_THRESHOLD); see tests/memory/test_search.py.
"""

import logging
import math
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from psycopg.rows import dict_row

from app.contracts import FrameDetail, SearchHit
from app.db import DB_ERRORS, get_conn
from app.memory import files
from app.memory import repository as repo
from app.memory.embeddings import Embedder

log = logging.getLogger("uvicorn.error")  # shows up in the API console

# ---------- scoring constants (calibrated in A8 on the real models) ----------

W_IMAGE, W_TEXT, W_OCR = 0.5, 0.3, 0.2
W_CONTENT, W_RECENCY = 0.85, 0.15
RECENCY_TAU_S = 600.0  # recency halves about every 7 minutes

# Raw cosine similarities are squeezed into small ranges, so they are stretched to 0..1:
# similarity <= low -> 0, >= high -> 1. Measured on our frames (exit signs in 3 languages,
# a living room, a street) with 20 questions in en/fr/ar: question vs PICTURE gives
# 0.24-0.32 for the right scene and 0.13-0.25 for the others; question vs CAPTION (text
# to text) gives 0.77-0.91 for the right caption and 0.55-0.84 for the others.
# These ranges were picked by grid search: every right scene ranks first and scores
# >= 0.32 when fresh (>= 0.27 when 5 min old); unrelated questions score <= 0.24.
IMAGE_SIM_RANGE = (0.21, 0.31)
TEXT_SIM_RANGE = (0.80, 0.92)

MATCH_LEVEL = 0.3  # a signal at least this strong is reported in SearchHit.matched_by
CANDIDATES_PER_INDEX = 50  # top-k taken from each index before the exact scoring

# Question words that are never what a sign says (the OCR part looks for the others).
STOPWORDS = frozenset(
    # English
    "a an the is are was were be been do does did what whats which who where when how "
    "why this that these those there here it its of on in at to for from with and or "
    "me my mine i you your we our can could would will tell read say says said saying "
    "written write wrote sign signs see saw seen look looked just now please about".split()
    # French
    + "le la les l un une des de du d au aux et ou où que qu quoi quel quelle quels "
    "quelles qui est sont était etait c ce cet cette ces il elle ils on y a je j me m "
    "moi mon ma mes tu te vous nous dit dire disait écrit ecrit écrite ecrite panneau "
    "lire lu vu voir peux peut sur dans en pour avec par ça ca là la-bas".split()
    # Arabic (standard + Lebanese)
    + "ماذا ما شو هل في على من الى إلى عن كان كانت يقول قال مكتوب كتب هذا هذه هيدا "
    "هيدي هيداك وين أين اين لافتة اللافتة يافطة اليافطة شفت رأيت انا أنا".split()
)
_ARABIC_PREFIXES = ("وال", "بال", "ال")  # "the" glued to the word: المخرج -> مخرج


# ---------- the text model (loaded once, on first search) ----------

_embedder: Embedder | None = None
_embedder_lock = threading.Lock()


def get_text_embedder() -> Embedder:
    """The multilingual CLIP text model only (the API never embeds images)."""
    global _embedder
    with _embedder_lock:
        if _embedder is None:
            _embedder = Embedder(with_image_model=False)
    return _embedder


def warm_up() -> None:
    """Load the text model ahead of the first question (called at API start)."""
    started = time.perf_counter()
    try:
        get_text_embedder()
    except Exception:  # a failed warm-up is retried by the first search
        log.exception("Search warm-up failed")
        return
    log.info("Search ready: text model loaded in %.1f s", time.perf_counter() - started)


# ---------- question words for the OCR part ----------

def _unaccent(word: str) -> str:
    """"sécurité" -> "securite" (OCR often drops accents on capital letters)."""
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c))


def query_terms(query: str) -> list[list[str]]:
    """Words worth looking for in OCR text, each with its spelling variants.

    "What did the EXIT sign say?" -> [["exit"]]
    "sécurité"                    -> [["sécurité", "securite"]]
    "المخرج"                       -> [["المخرج", "مخرج"]]
    """
    groups: list[list[str]] = []
    seen: set[str] = set()
    for word in re.findall(r"\w+", query.lower()):
        plain = _unaccent(word)
        if word in seen or word in STOPWORDS or plain in STOPWORDS:
            continue
        if len(word) < 2 and not word.isdigit():
            continue
        seen.add(word)
        variants = [word] if plain == word else [word, plain]
        for prefix in _ARABIC_PREFIXES:
            if word.startswith(prefix) and len(word) - len(prefix) >= 3:
                variants.append(word[len(prefix):])
                break
        groups.append(variants)
    return groups


# ---------- scoring ----------

def rescale(similarity: float | None, sim_range: tuple[float, float]) -> float:
    """Cosine similarity -> 0..1 using the calibrated range (None -> 0)."""
    if similarity is None:
        return 0.0
    low, high = sim_range
    return min(1.0, max(0.0, (similarity - low) / (high - low)))


@dataclass
class ScoreParts:
    image: float  # 0..1
    text: float  # 0..1
    ocr: float  # 0..1
    recency: float  # 0..1
    content: float  # 0..1, what the frame shows
    total: float  # 0..1, the SearchHit score


def score_frame(
    image_sim: float | None,
    text_sim: float | None,
    ocr_hits: int,
    n_terms: int,
    age_s: float,
) -> ScoreParts:
    image = rescale(image_sim, IMAGE_SIM_RANGE)
    text = rescale(text_sim, TEXT_SIM_RANGE)
    ocr = 0.5 + 0.5 * ocr_hits / n_terms if ocr_hits and n_terms else 0.0
    content = W_IMAGE * image + W_TEXT * text + W_OCR * ocr
    recency = math.exp(-max(0.0, age_s) / RECENCY_TAU_S)
    total = W_CONTENT * content + W_RECENCY * recency
    return ScoreParts(image, text, ocr, recency, content, total)


def _matched_by(parts: ScoreParts, time_filtered: bool) -> list[str]:
    matched = []
    if parts.image >= MATCH_LEVEL:
        matched.append("image")
    if parts.text >= MATCH_LEVEL:
        matched.append("text")
    if parts.ocr > 0:
        matched.append("ocr")
    if time_filtered:
        matched.append("time")
    return matched


# ---------- SQL ----------

def _window(since: datetime | None, until: datetime | None) -> tuple[str, dict]:
    """WHERE clause for the time window (uses the captured_at index)."""
    conditions, params = ["TRUE"], {}
    if since is not None:
        conditions.append("captured_at >= %(since)s")
        params["since"] = since
    if until is not None:
        conditions.append("captured_at <= %(until)s")
        params["until"] = until
    return " AND ".join(conditions), params


def _ocr_sql(groups: list[list[str]], params: dict) -> tuple[str | None, str]:
    """(tsquery matching ANY question word or None, SQL counting how many words match)."""
    per_word = []
    for i, variants in enumerate(groups):
        parts = []
        for j, variant in enumerate(variants):
            params[f"w{i}_{j}"] = variant
            parts.append(f"plainto_tsquery('simple', %(w{i}_{j})s)")
        per_word.append("(" + " || ".join(parts) + ")")
    if not per_word:
        return None, "0"
    any_word = " || ".join(per_word)
    hits = " + ".join(f"(ocr_tsv @@ {q})::int" for q in per_word)
    return any_word, hits


def _candidates(query_emb: np.ndarray, groups: list[list[str]], where: str,
                params: dict) -> list[dict]:
    """Frames found by any of the three indexes, with their raw similarities."""
    params = {**params, "q": query_emb, "k": CANDIDATES_PER_INDEX}
    any_word, hits = _ocr_sql(groups, params)
    ocr_cte = (
        f"UNION SELECT id FROM (SELECT id FROM frames WHERE {where} "
        f"AND ocr_tsv @@ ({any_word}) LIMIT %(k)s) AS ocr"
        if any_word else ""
    )
    sql = f"""
        WITH candidates AS (
            SELECT id FROM (SELECT id FROM frames WHERE {where} AND image_emb IS NOT NULL
                            ORDER BY image_emb <=> %(q)s LIMIT %(k)s) AS img
            UNION SELECT id FROM (SELECT id FROM frames WHERE {where} AND text_emb IS NOT NULL
                            ORDER BY text_emb <=> %(q)s LIMIT %(k)s) AS txt
            {ocr_cte}
        )
        SELECT {repo.FRAME_COLUMNS},
               1 - (image_emb <=> %(q)s) AS image_sim,
               1 - (text_emb <=> %(q)s) AS text_sim,
               {hits} AS ocr_hits
        FROM frames JOIN candidates USING (id)
    """
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Look further in the HNSW graphs (default 40) so a time filter still leaves k rows
        cur.execute("SET LOCAL hnsw.ef_search = 100")
        return cur.execute(sql, params).fetchall()


def _has_frames(where: str, params: dict) -> bool:
    with get_conn() as conn:
        return conn.execute(f"SELECT EXISTS (SELECT 1 FROM frames WHERE {where})",
                            params).fetchone()[0]


def rank_frames(
    query: str,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 5,
    now: datetime | None = None,
) -> list[SearchHit]:
    """search_frames() without the safety net: database errors are raised.

    Used by GET /api/search, which turns them into "503 database unavailable".
    """
    now = now or datetime.now(UTC)
    where, params = _window(since, until)
    if not _has_frames(where, params):
        return []  # nothing to search: do not even load the text model

    started = time.perf_counter()
    query_emb = get_text_embedder().embed_text(query)
    embed_ms = (time.perf_counter() - started) * 1000

    groups = query_terms(query)
    rows = _candidates(query_emb, groups, where, params)

    scored = []
    for row in rows:
        frame = repo.row_to_frame(row)
        age_s = (now - frame.captured_at).total_seconds()
        parts = score_frame(row["image_sim"], row["text_sim"], row["ocr_hits"], len(groups), age_s)
        if parts.content > 0:  # recency alone is not a match
            scored.append((parts, frame))
    scored.sort(key=lambda pair: (pair[0].total, pair[1].captured_at), reverse=True)

    time_filtered = since is not None or until is not None
    hits = [
        SearchHit(frame=frame.to_summary(), score=round(parts.total, 3),
                  matched_by=_matched_by(parts, time_filtered))
        for parts, frame in scored[: max(1, limit)]
    ]
    log.info(
        "search %r: %d candidates, best %s, embed %d ms, total %d ms",
        query, len(rows), f"#{hits[0].frame.id} {hits[0].score}" if hits else "none",
        embed_ms, (time.perf_counter() - started) * 1000,
    )
    return hits


# ---------- the contract (used by Student B's /api/ask) ----------

def search_frames(
    query: str,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 5,
) -> list[SearchHit]:
    """Best-matching frames for a question, best first ([] if the database is down)."""
    try:
        return rank_frames(query, since=since, until=until, limit=limit)
    except DB_ERRORS as error:
        log.warning("search_frames: database unavailable (%s)", error)
        return []


def get_latest_frame(max_age_s: int = 10) -> FrameDetail | None:
    """Most recent stored frame if it is younger than max_age_s ("in front of me now")."""
    try:
        rows = repo.list_frames(since=datetime.now(UTC) - timedelta(seconds=max_age_s), limit=1)
    except DB_ERRORS as error:
        log.warning("get_latest_frame: database unavailable (%s)", error)
        return None
    return rows[0].to_detail() if rows else None


def get_frame_image_path(frame_id: int) -> str:
    """Absolute path of a frame's full JPEG (the file may be gone if the frame was deleted)."""
    try:
        row = repo.get_frame(frame_id)
    except DB_ERRORS as error:
        log.warning("get_frame_image_path: database unavailable (%s)", error)
        row = None
    relative = row.image_path if row else f"frames/{frame_id}.jpg"  # the A7 naming rule
    return str(files.absolute(relative))


def count_frames() -> int:
    """Number of frames currently stored (0 if the database is down)."""
    try:
        return repo.count_frames()
    except DB_ERRORS as error:
        log.warning("count_frames: database unavailable (%s)", error)
        return 0
