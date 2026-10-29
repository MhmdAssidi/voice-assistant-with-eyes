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

    # ---------- Student B section ----------
    vlm_provider: str = "gemini"  # gemini | ollama
    gemini_api_key: str = ""
    gemini_model: str = ""
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5vl:3b"
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
