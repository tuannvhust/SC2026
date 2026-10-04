"""
src/services/gemini_embedder.py
Dense vector embedding service using the Gemini API.
Returns a 768-dimensional vector representing the text's semantics.
"""

import os
import requests
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


class GeminiDenseEmbedder:
    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        self.model_name = model_name or os.getenv(
            "GEMINI_EMBEDDING_MODEL",
            "models/gemini-embedding-001",
        )
        self.api_key = (
            os.getenv("GEMINI_API_KEY")
            if api_key is None
            else api_key
        )
        self.dimension = int(os.getenv("GEMINI_EMBEDDING_DIMENSION", "768"))
        self._disabled = False  # Fail fast after an API key receives a 403 response.

    def embed_text(self, text: str) -> List[float]:
        """Generate a dense vector for a text using the Gemini API."""
        if not self.api_key:
            return [0.0] * self.dimension

        if self._disabled:
            return [0.0] * self.dimension

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/{self.model_name}:embedContent?key={self.api_key}"
        payload = {
            "model": self.model_name,
            "content": {
                "parts": [{"text": text}]
            },
            "outputDimensionality": self.dimension,
        }

        try:
            res = requests.post(endpoint, json=payload, timeout=8)
            if res.status_code == 200:
                data = res.json()
                embedding = data.get("embedding", {}).get("values", [])
                if len(embedding) >= self.dimension:
                    return embedding[:self.dimension]
                elif len(embedding) > 0:
                    return embedding + [0.0] * (self.dimension - len(embedding))
            elif res.status_code == 403:
                print(f"[GeminiDenseEmbedder] 403 Permission Denied: Dự án Google Cloud của API Key bị từ chối truy cập. Tạm dừng gọi API.")
                self._disabled = True
            else:
                # Retry with the gemini-embedding-001 fallback model.
                fallback_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={self.api_key}"
                res_fb = requests.post(
                    fallback_endpoint,
                    json={"model": "models/gemini-embedding-001", "content": {"parts": [{"text": text}]}},
                    timeout=8
                )
                if res_fb.status_code == 200:
                    fb_data = res_fb.json()
                    embedding = fb_data.get("embedding", {}).get("values", [])
                    if len(embedding) != self.dimension:
                        raise ValueError(
                            f"Gemini fallback returned {len(embedding)} dimensions; "
                            f"expected {self.dimension}."
                        )
                    return embedding[:self.dimension] if len(embedding) >= self.dimension else embedding + [0.0] * (self.dimension - len(embedding))
                elif res_fb.status_code == 403:
                    print(f"[GeminiDenseEmbedder] 403 Permission Denied. Tạm dừng gọi API.")
                    self._disabled = True
        except Exception as e:
            print(f"[GeminiDenseEmbedder] Lỗi kết nối: {e}")

        return [0.0] * self.dimension

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate dense vectors for a batch of texts using batchEmbedContents."""
        if not self.api_key or self._disabled:
            return [[0.0] * self.dimension for _ in texts]

        # Try the batchEmbedContents endpoint for faster processing.
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/{self.model_name}:batchEmbedContents?key={self.api_key}"
        requests_payload = [
            {
                "model": self.model_name,
                "content": {"parts": [{"text": t}]},
                "outputDimensionality": self.dimension,
            }
            for t in texts
        ]

        try:
            res = requests.post(endpoint, json={"requests": requests_payload}, timeout=15)
            if res.status_code == 200:
                data = res.json()
                embeddings_raw = data.get("embeddings", [])
                results = []
                for item in embeddings_raw:
                    vals = item.get("values", [])
                    if len(vals) >= self.dimension:
                        results.append(vals[:self.dimension])
                    else:
                        results.append(vals + [0.0] * (self.dimension - len(vals)))
                return results
            elif res.status_code == 403:
                print(f"[GeminiDenseEmbedder] 403 Permission Denied khi batch embed. Chuyển sang fallback.")
                self._disabled = True
        except Exception as e:
            print(f"[GeminiDenseEmbedder] Batch embed error: {e}")

        # Fall back to sequential requests if the batch request fails.
        return [self.embed_text(t) for t in texts]
