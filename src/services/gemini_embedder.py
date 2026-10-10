"""
src/services/gemini_embedder.py
Nhánh 1 (Dense Vector): Gửi văn bản qua Gemini API (text-embedding-004)
-> Nhận về Vector 768 chiều đại diện cho ý nghĩa ngữ nghĩa.
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
        self._disabled = False  # Cờ fail-fast nếu key bị lỗi quyền 403

    def embed_text(self, text: str) -> List[float]:
        """
        Sinh Dense Vector 768 chiều cho một đoạn văn bản qua Gemini API.
        """
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
                # Thử fallback model gemini-embedding-001
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
        """
        Sinh Dense Vector cho danh sách văn bản (hỗ trợ batchEmbedContents).
        """
        if not self.api_key or self._disabled:
            return [[0.0] * self.dimension for _ in texts]

        # Thử gọi endpoint batchEmbedContents cho tốc độ nhanh vượt trội
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

        # Fallback tuần tự nếu batch thất bại
        return [self.embed_text(t) for t in texts]
