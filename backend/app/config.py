"""All configuration in one place (SHARED file).

Values come from environment variables or a `.env` file in the repo root
or in backend/. Never hard-code settings anywhere else.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ folder (this file is backend/app/config.py)
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- Shared ----------
    database_url: str = "postgresql://va:va@localhost:5432/va"
    api_internal_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ---------- Student A section ----------
    rtsp_url: str = "rtsp://localhost:8554/live"
    frames_dir: str = "../data/frames"  # relative paths are resolved from backend/
    retention_minutes: int = 30
    ingest_fps: float = 5.0  # frames per second the worker analyses (stream runs at 15)
    rtsp_reconnect_s: float = 2.0  # wait between reconnect attempts when the stream drops
    status_interval_s: float = 2.0  # how often the worker posts an ingest_status event
    # Frame selection (A3). Measured on a 320-px-wide gray copy of each frame.
    sharpness_min: float = 60.0  # Laplacian variance below this: too blurry, rejected
    sharpness_good: float = 120.0  # between min and good: mild blur, sharpened in A4
    novelty_min_bits: int = 10  # dHash bits (of 64) that must differ from the last kept frame
    keep_every_s: float = 5.0  # keep a frame at least this often, even in a still scene
    informative_min: float = 0.015  # edges + text score below this: blank wall, lens covered
    dark_brightness: float = 70.0  # mean gray below this counts as a dark frame (A3, A4)
    # OCR (A5). EasyOCR weights download once to MODELS_DIR/easyocr.
    ocr_min_confidence: float = 0.4  # blocks below this are dropped
    ocr_retry_below: float = 0.6  # best block below this: retry on a thresholded copy
    ocr_detect_width: int = 480  # find text boxes on a copy this wide (2x faster than 640)
    ocr_latin_sure: float = 0.7  # Latin reading at least this sure: skip the Arabic reader

    # ---------- Student B section ----------
    vlm_provider: str = "gemini"  # gemini | ollama
    gemini_api_key: str = ""
    # Stable + free tier. Measured Nov 2026: ~1 s; gemini-3.8-flash took ~60 s on the free tier.
    gemini_model: str = "gemini-3.5-flash-lite"
    # Tried at once when the main model is overloaded (503/504/timeout). "" = no backup.
    gemini_fallback_model: str = "gemini-3.1-flash-lite"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5vl:3b"
    # Total for all models together; the phone gives up after 30 s (STT ~8 s + search + VLM).
    vlm_timeout_s: float = 20.0
    whisper_model: str = "small"
    models_dir: str = "../data/models"  # downloaded model weights (git-ignored)
    # Keep each spoken question as data/questions/<time>_<lang>.m4a (for tests and
    # the B13 evaluation). Off by default: turn on only with the speaker's consent.
    save_question_audio: bool = False
    confidence_threshold: float = 0.25

    @property
    def frames_path(self) -> Path:
        """Absolute folder where frame JPEGs and thumbnails are stored."""
        path = Path(self.frames_dir)
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path

    @property
    def models_path(self) -> Path:
        """Absolute folder where model weights (e.g. Whisper) are cached."""
        path = Path(self.models_dir)
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path


settings = Settings()
