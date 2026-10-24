# Shared API contract v1.0

Source of truth: `backend/app/contracts.py` and `dashboard/src/types.ts`. Frozen Oct 25, 2026. Changes need a `contract/...` pull request approved by both students.

```text
Conventions: times are UTC ISO-8601 strings; IDs are integers; JSON keys are snake_case; API base http://SERVER:8000.

Ports: API 8000; dashboard 5173; Postgres 5432; MediaMTX RTSP 8554, WebRTC WHIP/WHEP 8889, WebRTC UDP 8189, HLS 8888.

.env.example:
DATABASE_URL=postgresql://va:va@localhost:5432/va
RTSP_URL=rtsp://localhost:8554/live
API_INTERNAL_URL=http://localhost:8000
FRAMES_DIR=../data/frames
RETENTION_MINUTES=30
VLM_PROVIDER=gemini            (gemini | ollama)
GEMINI_API_KEY=
GEMINI_MODEL=                  (current Flash model, set on setup day)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5vl:3b
WHISPER_MODEL=small
CONFIDENCE_THRESHOLD=0.25

REST endpoints:
- GET /api/health (shared) -> {"status":"ok"}
- GET /api/frames (A) query: since?, until?, limit=50 (max 200), before_id? -> FrameSummary[] newest first
- GET /api/frames/{id} (A) -> FrameDetail or 404
- GET /api/search (A) query: q, since?, until?, limit=10 -> SearchHit[] best first
- GET /media/... (A) static JPEGs (thumb_url and image_url point here)
- POST /api/ask (B) multipart: audio (file, m4a or wav) OR text (string), optional lang_hint (en|fr|ar) -> AskResponse. The text field lets anyone test with curl without a phone.
- GET /api/questions (B) query: limit=50 -> QaRecord[] newest first
- GET /api/status (B) -> SystemStatus
- POST /api/internal/events (B) body: Event -> {"ok":true}; accepted from localhost only
- WS /ws/events (B) -> stream of Event JSON messages

Models (backend/app/contracts.py, mirrored field-for-field in dashboard/src/types.ts):

class DetectedObject(BaseModel):
    label: str                    # English class name
    confidence: float             # 0..1
    bbox: list[int]               # [x1, y1, x2, y2] pixels
    position: Literal["left", "center", "right"]
    near: bool                    # box area > 25% of frame

class OcrBlock(BaseModel):
    text: str
    confidence: float
    bbox: list[int]

class FrameSummary(BaseModel):
    id: int
    captured_at: datetime
    thumb_url: str                # "/media/thumbs/123.jpg"
    ocr_text: str                 # "" if none
    object_labels: list[str]
    enhanced: bool

class FrameDetail(FrameSummary):
    image_url: str
    width: int
    height: int
    sharpness: float
    brightness: float
    ocr_blocks: list[OcrBlock]
    objects: list[DetectedObject]

class SearchHit(BaseModel):
    frame: FrameSummary
    score: float                  # 0..1, higher is better
    matched_by: list[Literal["image", "text", "ocr", "time"]]

class Evidence(BaseModel):
    frame_id: int
    captured_at: datetime
    thumb_url: str
    score: float

class AskResponse(BaseModel):
    id: int
    question: str
    language: Literal["en", "fr", "ar"]
    answer: str                   # 1-2 short sentences, ready to speak
    confident: bool
    evidence: list[Evidence]
    timings_ms: dict[str, int]    # keys: stt, search, vlm, total

class QaRecord(AskResponse):
    asked_at: datetime

class SystemStatus(BaseModel):
    stream_connected: bool
    ingest_running: bool
    frames_seen: int
    frames_kept: int
    frame_count: int              # rows currently in DB
    last_frame_at: datetime | None
    avg_process_ms: int
    last_question_at: datetime | None

class Event(BaseModel):
    type: Literal["frame_stored", "ingest_status", "question_answered", "warning"]
    ts: datetime
    data: dict

Event payloads (Event.data):
- frame_stored (sent by A's worker): a FrameSummary
- ingest_status (A's worker, every 2 s): {stream_connected, ingest_running, frames_seen, frames_kept, avg_process_ms}
- question_answered (B's ask): a QaRecord
- warning (A's worker): {kind: "closed_door" | "stairs", confidence, frame_id, position}
The phone builds the spoken warning sentence itself from kind and the current language, so wording rules live in B's i18n.

Python interface in backend/app/memory/search.py (A provides, B calls):
def search_frames(query: str, since: datetime | None = None, until: datetime | None = None, limit: int = 5) -> list[SearchHit]
def get_latest_frame(max_age_s: int = 10) -> FrameDetail | None
def get_frame_image_path(frame_id: int) -> str      # absolute path to the JPEG
def count_frames() -> int

Database (backend/db/init/, run automatically by the Postgres container on first start):

-- 001_frames.sql (A)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE frames (
  id SERIAL PRIMARY KEY,
  captured_at TIMESTAMPTZ NOT NULL,
  image_path TEXT NOT NULL,
  thumb_path TEXT NOT NULL,
  width INT, height INT,
  sharpness REAL, brightness REAL,
  enhanced BOOLEAN DEFAULT FALSE,
  dhash BIGINT,
  ocr_text TEXT DEFAULT '',
  ocr_blocks JSONB DEFAULT '[]',
  objects JSONB DEFAULT '[]',
  caption_text TEXT DEFAULT '',        -- OCR + objects, used for the text embedding
  image_emb vector(512),
  text_emb vector(512),
  ocr_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', ocr_text)) STORED
);
CREATE INDEX frames_time_idx ON frames (captured_at DESC);
CREATE INDEX frames_img_hnsw ON frames USING hnsw (image_emb vector_cosine_ops);
CREATE INDEX frames_txt_hnsw ON frames USING hnsw (text_emb vector_cosine_ops);
CREATE INDEX frames_ocr_gin ON frames USING gin (ocr_tsv);

-- 002_qa.sql (B)
CREATE TABLE qa_log (
  id SERIAL PRIMARY KEY,
  asked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  question TEXT NOT NULL,
  language VARCHAR(2) NOT NULL,
  answer TEXT NOT NULL,
  confident BOOLEAN NOT NULL,
  evidence JSONB DEFAULT '[]',
  timings_ms JSONB DEFAULT '{}'
);
qa_log has no foreign key to frames, because retention deletes frames while Q&A history stays.

Answer rules (B implements; everyone respects them in any user-facing text):
- At most 2 sentences, describing only what is in the evidence frames.
- Never describe surroundings as "safe" / "sans danger" / "en sécurité" / "آمن".
- confident=false -> the answer starts with the localized "I'm not sure" / "Je ne suis pas sûr" / "لست متأكدًا".
- Never identify a person; people are "a person".
- Answer language = the question's detected language (en, fr, ar).
```
