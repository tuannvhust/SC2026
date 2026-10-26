"""Shared CrossEncoder instance reused by every RAG entry point in a worker."""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Optional

from .reranker import DEFAULT_MODEL_NAME, Reranker

logger = logging.getLogger(__name__)

_shared_reranker: Optional[Reranker] = None
_shared_reranker_lock = Lock()
RERANKER_INIT_COUNT = 0


def get_shared_reranker(model_name: Optional[str] = None) -> Reranker:
    """Return the worker-wide reranker (double-checked, thread-safe)."""
    global _shared_reranker, RERANKER_INIT_COUNT
    wanted = (model_name or os.getenv("HF_RERANKER_MODEL", DEFAULT_MODEL_NAME)).strip()
    if _shared_reranker is not None and _shared_reranker.model_name == wanted:
        return _shared_reranker
    with _shared_reranker_lock:
        if _shared_reranker is not None and _shared_reranker.model_name == wanted:
            return _shared_reranker
        _shared_reranker = Reranker(model_name=wanted)
        RERANKER_INIT_COUNT += 1
        logger.info(
            "reranker shared instance init #%s model=%s",
            RERANKER_INIT_COUNT,
            wanted,
        )
        return _shared_reranker


def reset_shared_reranker() -> None:
    """Test-only hook to drop the cached instance."""
    global _shared_reranker
    with _shared_reranker_lock:
        _shared_reranker = None
