"""Rerank retrieved documents with the Hugging Face Inference API."""

from __future__ import annotations

import os
from numbers import Real
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "BAAI/bge-reranker-v2-m3"
)


class Reranker:
    def __init__(
        self,
        api_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ):
        self.api_url = (
            api_url
            or os.getenv("HF_RERANKER_API_URL", DEFAULT_API_URL).strip()
        )
        self.token = token or os.getenv("HF_TOKEN", "").strip()
        self.timeout = timeout or float(os.getenv("HF_RERANKER_TIMEOUT", "30"))

    def _extract_scores(self, payload: Any, expected_count: int) -> List[float]:
        """Extract scores from direct, dictionary, and nested HF responses."""
        # 1. TrÆ°á»ng há»£p response dáº¡ng dict {"scores": [...]}
        if isinstance(payload, dict) and isinstance(payload.get("scores"), list):
            payload = payload["scores"]

        # 2. Xá»­ lÃ½ trÆ°á»ng há»£p Hugging Face bá»c toÃ n bá»™ káº¿t quáº£ trong máº£ng 2 chiá»u [[doc1, doc2, ...]]
        if (
            isinstance(payload, list)
            and len(payload) == 1
            and isinstance(payload[0], list)
            and len(payload[0]) == expected_count
        ):
            payload = payload[0]

        # 3. TrÆ°á»ng há»£p payload Ä‘Ã£ lÃ  máº£ng sá»‘ pháº³ng [0.18, 0.11, ...]
        if (
            isinstance(payload, list)
            and len(payload) == expected_count
            and all(isinstance(item, Real) for item in payload)
        ):
            return [float(item) for item in payload]

        # 4. BÃ³c tÃ¡ch Ä‘iá»ƒm sá»‘ tá»« danh sÃ¡ch dictionary
        scores: List[float] = []
        if isinstance(payload, list):
            for item in payload:
                candidates = item if isinstance(item, list) else [item]
                score: Any = None

                # Æ¯u tiÃªn láº¥y Ä‘iá»ƒm tá»« LABEL_1 náº¿u mÃ´ hÃ¬nh lÃ  binary classification
                for candidate in candidates:
                    if (
                        isinstance(candidate, dict)
                        and candidate.get("label") == "LABEL_1"
                        and isinstance(candidate.get("score"), Real)
                    ):
                        score = candidate["score"]
                        break

                # Náº¿u khÃ´ng cÃ³ LABEL_1, láº¥y score tá»« dictionary hoáº·c giÃ¡ trá»‹ sá»‘ báº¥t ká»³
                if score is None:
                    for candidate in candidates:
                        if isinstance(candidate, dict) and isinstance(
                            candidate.get("score"), Real
                        ):
                            score = candidate["score"]
                            break
                        if isinstance(candidate, Real):
                            score = candidate
                            break

                if score is None:
                    raise RuntimeError(
                        "Hugging Face reranker returned a non-numeric score."
                    )
                scores.append(float(score))

        if len(scores) != expected_count:
            raise RuntimeError(
                "Could not parse Hugging Face reranker scores: "
                f"{payload!r}"
            )
        return scores

    def _request_scores(self, query: str, texts: List[str]) -> List[float]:
        if not self.token:
            raise RuntimeError(
                "HF_TOKEN is not configured; set it in the backend .env file."
            )

        response = requests.post(
            self.api_url,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
            json={
                "inputs": [
                    {"text": query, "text_pair": text}
                    for text in texts
                ],
            },
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(
                f"Hugging Face reranker returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        return self._extract_scores(response.json(), len(texts))

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        """Return the highest-scoring documents from Hugging Face."""
        if not documents:
            return []

        texts = [doc.get("embedding_text") or str(doc) for doc in documents]
        scores = self._request_scores(query, texts)

        ranked = sorted(
            zip(scores, documents),
            key=lambda item: item[0],
            reverse=True,
        )

        # Gáº¯n kÃ¨m score vÃ o dictionary tÃ i liá»‡u Ä‘á»ƒ dá»… theo dÃµi
        reranked_docs = []
        for score, doc in ranked[:top_n]:
            doc_copy = dict(doc)
            doc_copy["rerank_score"] = score
            reranked_docs.append(doc_copy)

        return reranked_docs
