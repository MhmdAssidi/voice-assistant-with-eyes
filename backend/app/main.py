"""FastAPI application entry point (SHARED file, written once in S0).

Run from the backend/ folder:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Then open http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import ask, events, frames, questions, search, status
from app.config import settings

app = FastAPI(
    title="Voice Assistant with Eyes",
    version="1.0.0",
    description="Multimedia Database and Image Processing project, Fall 2026/2027.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Student A
app.include_router(frames.router)
app.include_router(search.router)
# Student B
app.include_router(ask.router)
app.include_router(questions.router)
app.include_router(status.router)
app.include_router(events.router)

# Stored frame images, served at /media/frames/... and /media/thumbs/...
settings.frames_path.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.frames_path), name="media")


@app.get("/api/health", tags=["shared"])
def health() -> dict:
    return {"status": "ok"}
