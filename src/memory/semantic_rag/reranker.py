"""Rerank retrieved documents with a local CrossEncoder model."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Protocol

os.environ["HF_HUB_OFFLINE"] = "1"

DEFAULT_MODEL_NAME = "BAAI/bge-reranker-base"


class _CrossEncoder(Protocol):
    def predict(self, sentences: List[List[str]]) -> Any:
        ...


class Reranker:
    def __init__(self, model_name: str | None = None):
        self.model_name = (
            model_name or os.getenv("HF_RERANKER_MODEL", DEFAULT_MODEL_NAME)
        ).strip()
        self._model: _CrossEncoder | None = None

    def _load_model(self) -> _CrossEncoder:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                device="cpu",
                automodel_args={"local_files_only": True},
            )
        return self._model

    def warmup(self) -> None:
        """Load the model and run a minimal prediction before serving requests."""
        self._load_model().predict([["warmup", "warmup"]])

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        """Return the highest-scoring documents using the local model."""
        if not documents:
            return []

        pairs = [
            [query, doc.get("embedding_text") or str(doc)]
            for doc in documents
        ]
        scores = self._load_model().predict(pairs)
        if len(scores) != len(documents):
            raise RuntimeError(
                "Local reranker returned an unexpected number of scores: "
                f"expected {len(documents)}, got {len(scores)}."
            )

        ranked = sorted(
            zip((float(score) for score in scores), documents),
            key=lambda item: item[0],
            reverse=True,
        )

        reranked_docs = []
        for score, doc in ranked[:top_n]:
            doc_copy = dict(doc)
            doc_copy["rerank_score"] = score
            reranked_docs.append(doc_copy)

        return reranked_docs
