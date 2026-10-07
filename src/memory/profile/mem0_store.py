"""Mem0-backed long-term customer profile facts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable

from src.memory.working.sqlite_store import _project_root

_memory_instance: Any = None
_memory_lock = RLock()


def _memory_paths() -> tuple[Path, Path]:
    vector_path = Path(
        os.getenv(
            "MEM0_VECTOR_PATH",
            str(_project_root() / "data" / "memory" / "mem0_qdrant"),
        )
    )
    history_path = Path(
        os.getenv(
            "MEM0_HISTORY_DB_PATH",
            str(_project_root() / "data" / "memory" / "mem0_history.sqlite3"),
        )
    )
    if not vector_path.is_absolute():
        vector_path = _project_root() / vector_path
    if not history_path.is_absolute():
        history_path = _project_root() / history_path
    vector_path.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    return vector_path, history_path


def _get_memory() -> Any:
    global _memory_instance
    if _memory_instance is None:
        with _memory_lock:
            if _memory_instance is None:
                api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise RuntimeError(
                        "GEMINI_API_KEY or GOOGLE_API_KEY is required for Mem0 profile memory."
                    )

                from mem0 import Memory

                vector_path, history_path = _memory_paths()
                config = {
                    "llm": {
                        "provider": "gemini",
                        "config": {
                            "model": os.getenv("MEM0_LLM_MODEL", "gemini-2.5-flash"),
                            "api_key": api_key,
                            "temperature": 0.1,
                        },
                    },
                    "embedder": {
                        "provider": "gemini",
                        "config": {
                            "model": os.getenv(
                                "GEMINI_EMBEDDING_MODEL",
                                "models/gemini-embedding-001",
                            ),
                            "api_key": api_key,
                            "embedding_dims": int(
                                os.getenv("GEMINI_EMBEDDING_DIMENSION", "768")
                            ),
                        },
                    },
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "collection_name": "customer_profile_memories",
                            "embedding_model_dims": int(
                                os.getenv("GEMINI_EMBEDDING_DIMENSION", "768")
                            ),
                            "path": str(vector_path),
                            "on_disk": True,
                        },
                    },
                    "history_db_path": str(history_path),
                    "custom_instructions": (
                        "Store only explicit, durable customer profile facts. "
                        "Do not store prices, promotions, inventory, order status, "
                        "or arbitrary conversation text as profile memory."
                    ),
                }
                _memory_instance = Memory.from_config(config)
    return _memory_instance


class Mem0ProfileStore:
    """Read and write facts scoped to one customer with session provenance."""

    def get_profile_facts(self, customer_id: str) -> Dict[str, Any]:
        with _memory_lock:
            response = _get_memory().get_all(
                filters={"user_id": customer_id},
                top_k=100,
            )

        facts: Dict[str, Any] = {}
        for item in response.get("results", []):
            metadata = item.get("metadata") or {}
            if metadata.get("memory_type") != "profile_fact":
                continue
            key = metadata.get("profile_key")
            if isinstance(key, str) and key:
                facts[key] = metadata.get("profile_value", item.get("memory"))
        return facts

    def add_profile_facts(
        self,
        customer_id: str,
        facts: Iterable[Dict[str, Any]],
        session_id: str,
    ) -> None:
        memory = _get_memory()
        for fact in facts:
            key = fact["key"]
            value = fact["value"]
            content = (
                f"Explicit customer profile fact. "
                f"{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
            )
            metadata = {
                "memory_type": "profile_fact",
                "profile_key": key,
                "profile_value": value,
                "provenance_session_id": session_id,
            }
            with _memory_lock:
                memory.add(
                    content,
                    user_id=customer_id,
                    metadata=metadata,
                )


def get_profile_store() -> Mem0ProfileStore:
    return Mem0ProfileStore()


def reset_profile_memory_for_tests() -> None:
    """Reset the lazy Mem0 singleton between isolated tests."""
    global _memory_instance
    with _memory_lock:
        _memory_instance = None
