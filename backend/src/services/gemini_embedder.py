"""Generate dense text embeddings with the Gemini API."""

import os
import time
from typing import Any, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "models/gemini-embedding-001"
DEFAULT_DIMENSION = 768
DEFAULT_TIMEOUT_SECONDS = 120


class GeminiDenseEmbedder:
    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        configured_model = model_name or os.getenv(
            "GEMINI_EMBEDDING_MODEL", DEFAULT_MODEL
        )
        self.model_name = (
            configured_model
            if configured_model.startswith("models/")
            else f"models/{configured_model}"
        )
        self.api_key = (
            os.getenv("GEMINI_API_KEY") if api_key is None else api_key
        )
        self.dimension = int(
            os.getenv("GEMINI_EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION))
        )
        self.timeout = float(
            os.getenv(
                "GEMINI_EMBEDDING_TIMEOUT",
                str(DEFAULT_TIMEOUT_SECONDS),
            )
        )
        self._disabled = False
        
        # Sử dụng Session để tái sử dụng kết nối mạng, tránh ConnectionError
        self.session = requests.Session()

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        max_attempts = 6
        base_delay = 2.0  # Thời gian chờ cơ bản (giây)

        for attempt in range(max_attempts):
            try:
                response = self.session.post(
                    endpoint,
                    params={"key": self.api_key},
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.Timeout:
                if attempt == max_attempts - 1:
                    raise TimeoutError(
                        f"Gemini embedding request timed out after {self.timeout:g}s."
                    ) from None
                time.sleep(base_delay * (2 ** attempt))
                continue
            except requests.RequestException as exc:
                if attempt == max_attempts - 1:
                    raise RuntimeError(
                        f"Gemini embedding request failed ({type(exc).__name__})."
                    ) from None
                time.sleep(base_delay * (2 ** attempt))
                continue

            # Bắt lỗi Rate Limit (429) hoặc lỗi Server (50x) để thử lại
            if response.status_code in [429, 500, 502, 503, 504]:
                if attempt < max_attempts - 1:
                    sleep_time = base_delay * (2 ** attempt)
                    print(f"[\u26A0\ufe0f] API Rate Limit/Error (HTTP {response.status_code}). Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                    continue

            if response.status_code == 403:
                self._disabled = True
            if response.status_code == 404:
                raise RuntimeError(
                    f"Gemini embedding model '{self.model_name}' was not found "
                    "(HTTP 404). Check GEMINI_EMBEDDING_MODEL."
                )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Gemini embedding API returned HTTP {response.status_code}."
                )
            return response.json()

    def _embed_content(self, text: str) -> List[float]:
        response = self._post(
            f"{API_URL}/{self.model_name}:embedContent",
            {
                "model": self.model_name,
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": self.dimension,
            },
        )
        vector = response.get("embedding", {}).get("values", [])
        if len(vector) != self.dimension:
            raise ValueError(
                f"Gemini returned {len(vector)} dimensions; "
                f"expected {self.dimension}."
            )
        return vector

    def embed_text(self, text: str) -> List[float]:
        """Generate an embedding for one text string."""
        self._ensure_ready()
        return self._embed_content(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple text strings in one API request."""
        self._ensure_ready()
        if not texts:
            return []

        requests_payload = [
            {
                "model": self.model_name,
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": self.dimension,
            }
            for text in texts
        ]
        response = self._post(
            f"{API_URL}/{self.model_name}:batchEmbedContents",
            {"requests": requests_payload},
        )
        embeddings = [
            item.get("values", [])
            for item in response.get("embeddings", [])
        ]
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Gemini returned {len(embeddings)} embeddings for "
                f"{len(texts)} inputs."
            )
        for vector in embeddings:
            if len(vector) != self.dimension:
                raise ValueError(
                    f"Gemini returned {len(vector)} dimensions; "
                    f"expected {self.dimension}."
                )
        return embeddings

    def _ensure_ready(self) -> None:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        if self._disabled:
            raise RuntimeError(
                "Gemini embedding is disabled after an HTTP 403 response."
            )