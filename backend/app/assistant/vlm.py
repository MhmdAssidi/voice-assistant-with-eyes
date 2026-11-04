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
    """Gemini with a backup model.

    The free tier is sometimes overloaded (measured: the usual ~1 s became 24 s,
    or a 503/504 error). Then the next model in `models` is tried at once, each
    with its share of the time budget, so the phone still gets an answer.
    """

    name = "gemini"

    def __init__(self, api_key: str, models: list[str], timeout_s: float) -> None:
        models = [m for m in models if m]
        if not api_key or not models:
            raise VlmError("GEMINI_API_KEY or GEMINI_MODEL is empty: set both in .env")
        from google import genai  # imported here: tests and Ollama users don't need it

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._models = models
        self._timeout_ms = int(timeout_s * 1000 / len(models))  # per model

    def generate(self, system: str, user: str, images: list[bytes]) -> VlmAnswer:
        types = self._genai.types
        errors = self._genai.errors
        parts = [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg") for jpeg in images]
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=VlmAnswer,
            temperature=0.2,  # low: describe, don't be creative
            http_options=types.HttpOptions(timeout=self._timeout_ms),
        )
        failures: list[str] = []
        for model in self._models:
            try:
                response = self._client.models.generate_content(
                    model=model, contents=[*parts, user], config=config
                )
                return parse_answer(response.text or "")
            except errors.ClientError as error:
                # 4xx (bad key, quota used up, unknown model): another model won't help
                raise VlmError(f"Gemini refused ({model}): {error}") from error
            except Exception as error:  # 5xx overloaded, timeout, network, bad reply
                failures.append(f"{model}: {str(error)[:120]}")
        raise VlmError("Gemini failed: " + " | ".join(failures))


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
    return GeminiProvider(
        settings.gemini_api_key,
        [settings.gemini_model, settings.gemini_fallback_model],
        settings.vlm_timeout_s,
    )
