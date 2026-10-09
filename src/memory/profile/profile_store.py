"""Dual-store customer profile facts in PostgreSQL and Qdrant."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from qdrant_client import models

from src.memory.working.postgres_store import (
    PostgresMemoryStore,
    get_postgres_memory_store,
)

PROFILE_COLLECTION = "customer_profile_memories"
_PROFILE_NAMESPACE = uuid.UUID("880650be-a6c8-4a85-a3a3-127d1c9132b1")


class ProfileStore:
    """Keep structured customer facts in PostgreSQL and vectors in Qdrant."""

    def __init__(
        self,
        postgres_store: Optional[PostgresMemoryStore] = None,
        connections: Any = None,
    ):
        self._postgres_store = postgres_store
        self._connections = connections

    def _get_postgres_store(self) -> PostgresMemoryStore:
        return self._postgres_store or get_postgres_memory_store()

    def _get_connections(self):
        if self._connections is not None:
            return self._connections

        from src.config import get_shared_connections

        return get_shared_connections()

    def get_profile_facts(self, customer_id: str) -> Dict[str, Any]:
        """Return the structured, authoritative profile values from PostgreSQL."""
        return self._get_postgres_store().get_profile_facts(customer_id)

    def add_profile_facts(
        self,
        customer_id: str,
        facts: Iterable[Dict[str, Any]],
        session_id: str,
    ) -> None:
        facts_by_key = {}
        for fact in facts:
            if not isinstance(fact, dict):
                raise ValueError("Each profile fact must be an object.")
            key = fact.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Each profile fact must have a non-empty string key.")
            if "value" not in fact:
                raise ValueError("Each profile fact must include a value.")
            facts_by_key[key.strip()] = {"key": key.strip(), "value": fact["value"]}
        fact_list = list(facts_by_key.values())
        if not fact_list:
            return

        connections = self._get_connections()
        connections.vector_store.init_collection(
            PROFILE_COLLECTION,
            dense_dim=int(os.getenv("GEMINI_EMBEDDING_DIMENSION", "768")),
        )

        points = []
        for fact in fact_list:
            key = fact["key"]
            value = fact["value"]
            content = (
                f"Customer profile fact. {key}: "
                f"{json.dumps(value, ensure_ascii=False, sort_keys=True)}"
            )
            vector = connections.dense_embedder.embed_text(content)
            point_id = str(
                uuid.uuid5(_PROFILE_NAMESPACE, f"{customer_id}\0{key}")
            )
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={"dense": vector},
                    payload={
                        "customer_id": customer_id,
                        "profile_key": key,
                        "profile_value": value,
                        "provenance_session_id": session_id,
                        "memory_type": "profile_fact",
                    },
                )
            )

        connections.vector_store.client.upsert(
            collection_name=PROFILE_COLLECTION,
            points=points,
        )
        self._get_postgres_store().save_profile_facts(
            customer_id=customer_id,
            facts=fact_list,
            session_id=session_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )


def get_profile_store() -> ProfileStore:
    return ProfileStore()
