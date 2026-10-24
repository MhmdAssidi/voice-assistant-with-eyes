# Architecture

```text
 Phone (Flutter, B) ──WHIP video──▶ MediaMTX (B) ──RTSP──▶ Ingest worker (A)
        │   ▲                          │                       │ select, enhance, blur faces,
        │   │                          │ WHEP                  │ OCR, objects, embeddings
  audio │   │ answer JSON,             ▼                       ▼
        │   │ warnings          Dashboard (React)        PostgreSQL + pgvector (A)
        ▼   │                     A: Live, Timeline,       + JPEG files on disk
   FastAPI backend ◀── REST + /ws/events ── Search           ▲
   ask, STT, VLM, events (B)              B: History, Status │
   frames, search (A) ──────────── queries ──────────────────┘
        │
        └──▶ Vision-language model (Gemini Flash, or Ollama offline)
```

## Processes

| Process | Command | Port |
| --- | --- | --- |
| PostgreSQL + MediaMTX | `docker compose up -d` | 5432, 8554, 8889, 8888, 8189/udp |
| Backend API | `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` (in `backend/`) | 8000 |
| Ingest worker | `python -m app.ingest.worker` (in `backend/`, from A2) | — |
| Dashboard | `npm run dev` (in `dashboard/`) | 5173 |
| Phone app | `flutter run` (in `mobile/`, from B0) | — |

## The three seams between Student A and Student B

1. **The RTSP stream** — B's phone and MediaMTX deliver it; A's worker consumes it.
2. **`POST /api/internal/events`** — A's worker sends events; B's hub forwards them to the dashboard and phone.
3. **`app/memory/search.py`** — A provides `search_frames()` and `get_latest_frame()`; B's `/api/ask` calls them.

Everything else is private to its owner. See [api-contract.md](api-contract.md).
