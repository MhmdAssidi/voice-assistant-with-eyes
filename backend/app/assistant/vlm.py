"""Vision-language model providers (owner: Student B, task B7).

One small interface, two implementations, chosen with VLM_PROVIDER in .env:
- gemini: Google Gemini through the official google-genai SDK (fast, needs internet + key)
- ollama: a local model (e.g. qwen2.5vl) through Ollama's HTTP API (offline backup)
Both are asked for JSON {"answer": str, "confident": bool}.
"""

import base64
import json
import re
from functools import lru_cache
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings


class VlmAnswer(BaseModel):
    answer: str
    confident: bool


class VlmError(RuntimeError):
    """The model could not be reached or gave no usable answer."""


class VlmProvider(Protocol):
    name: str

    def generate(self, system: str, user: str, images: list[bytes]) -> VlmAnswer:
        """images are JPEG bytes, in the order the user prompt describes them."""
        ...


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_s: float) -> None:
        if not api_key or not model:
            raise VlmError("GEMINI_API_KEY or GEMINI_MODEL is empty: set both in .env")
        from google import genai  # imported here: tests and Ollama users don't need it

        self._genai = genai
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai.types.HttpOptions(timeout=int(timeout_s * 1000)),  # ms
        )
        self._model = model

    def generate(self, system: str, user: str, images: list[bytes]) -> VlmAnswer:
        types = self._genai.types
        parts = [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg") for jpeg in images]
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[*parts, user],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=VlmAnswer,
                    temperature=0.2,  # low: describe, don't be creative
                ),
            )
        except Exception as error:  # network, quota (429), bad key...
            raise VlmError(f"Gemini failed: {error}") from error
        return parse_answer(response.text or "")


class OllamaProvider:
    name = "ollama"

    def __init__(self, url: str, model: str, timeout_s: float) -> None:
        self._url = url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s

    def generate(self, system: str, user: str, images: list[bytes]) -> VlmAnswer:
        body = {
            "model": self._model,
            "stream": False,
            "format": VlmAnswer.model_json_schema(),  # Ollama "structured outputs"
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": user,
                    "images": [base64.b64encode(jpeg).decode() for jpeg in images],
                },
            ],
        }
        try:
            response = httpx.post(f"{self._url}/api/chat", json=body, timeout=self._timeout_s)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise VlmError(f"Ollama failed: {error}") from error
        return parse_answer(response.json().get("message", {}).get("content", ""))


def parse_answer(text: str) -> VlmAnswer:
    """Reads the model's JSON, tolerating ```json fences around it."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return VlmAnswer.model_validate(json.loads(cleaned))
    except (json.JSONDecodeError, ValidationError) as error:
        raise VlmError(f"unusable model reply: {text[:200]!r}") from error


@lru_cache(maxsize=1)
def get_provider() -> VlmProvider:
    """The provider chosen in .env, created once."""
    if settings.vlm_provider == "ollama":
        return OllamaProvider(settings.ollama_url, settings.ollama_model, settings.vlm_timeout_s)
    return GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.vlm_timeout_s)
