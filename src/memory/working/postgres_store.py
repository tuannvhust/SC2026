"""SQLAlchemy persistence for working events, episodes, and profile facts."""

from __future__ import annotations

import json
import os
from threading import RLock
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine, make_url


def default_database_url() -> str:
    database_url = (
        os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    ).strip()
    if not database_url:
        raise RuntimeError(
            "SUPABASE_DATABASE_URL or DATABASE_URL must be configured "
            "for PostgreSQL memory storage."
        )
    return database_url


def _normalized_database_url(database_url: str):
    url = make_url(database_url)
    if url.get_backend_name() == "postgresql":
        if url.drivername in {"postgres", "postgresql"}:
            url = url.set(drivername="postgresql+psycopg2")
        query = dict(url.query)
        query.setdefault("sslmode", "require")
        url = url.set(query=query)
    return url


class PostgresMemoryStore:
    """Persist graph state and customer profile facts in SQL databases."""

    def __init__(self, database_url: Optional[str] = None):
        configured_url = database_url or default_database_url()
        url = _normalized_database_url(configured_url)
        connect_args = (
            {"connect_timeout": 10}
            if url.get_backend_name() == "postgresql"
            else {}
        )
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.metadata = MetaData()
        self.working_events = Table(
            "working_events",
            self.metadata,
            Column("event_id", String, primary_key=True),
            Column("session_id", String, nullable=False),
            Column("turn_id", String, nullable=False),
            Column("turn_number", Integer, nullable=False),
            Column("customer_id", String),
            Column("created_at", String, nullable=False),
            Column("payload_json", String, nullable=False),
            UniqueConstraint("session_id", "turn_id"),
            UniqueConstraint("session_id", "turn_number"),
        )
        Index(
            "idx_working_events_customer",
            self.working_events.c.customer_id,
            self.working_events.c.created_at,
        )
        self.episodic_memory = Table(
            "episodic_memory",
            self.metadata,
            Column("session_id", String, primary_key=True),
            Column("customer_id", String),
            Column("ended_at", String, nullable=False),
            Column("payload_json", String, nullable=False),
        )
        Index(
            "idx_episodic_memory_customer",
            self.episodic_memory.c.customer_id,
            self.episodic_memory.c.ended_at,
        )
        self.profile_facts = Table(
            "profile_facts",
            self.metadata,
            Column("customer_id", String, primary_key=True),
            Column("profile_key", String, primary_key=True),
            Column("profile_value_json", String, nullable=False),
            Column("provenance_session_id", String, nullable=False),
            Column("updated_at", String, nullable=False),
        )
        self.metadata.create_all(self.engine)

    def append_turn(
        self,
        *,
        event_id: str,
        session_id: str,
        turn_id: str,
        customer_id: Optional[str],
        created_at: str,
        payload: Dict[str, Any],
    ) -> int:
        """Append or idempotently update an event and return its turn number."""
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "hashtextextended(:session_id, 0))"
                    ),
                    {"session_id": session_id},
                )

            existing = connection.execute(
                text(
                    """
                    SELECT turn_number FROM working_events
                    WHERE session_id = :session_id AND turn_id = :turn_id
                    """
                ),
                {"session_id": session_id, "turn_id": turn_id},
            ).mappings().first()
            if existing:
                turn_number = int(existing["turn_number"])
                connection.execute(
                    text(
                        """
                        UPDATE working_events
                        SET customer_id = :customer_id, created_at = :created_at,
                            payload_json = :payload_json
                        WHERE session_id = :session_id AND turn_id = :turn_id
                        """
                    ),
                    {
                        "customer_id": customer_id,
                        "created_at": created_at,
                        "payload_json": payload_json,
                        "session_id": session_id,
                        "turn_id": turn_id,
                    },
                )
                return turn_number

            latest = connection.execute(
                text(
                    """
                    SELECT MAX(turn_number) AS turn_number
                    FROM working_events WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().one()
            turn_number = int(latest["turn_number"] or 0) + 1
            connection.execute(
                text(
                    """
                    INSERT INTO working_events (
                        event_id, session_id, turn_id, turn_number, customer_id,
                        created_at, payload_json
                    ) VALUES (
                        :event_id, :session_id, :turn_id, :turn_number,
                        :customer_id, :created_at, :payload_json
                    )
                    """
                ),
                {
                    "event_id": event_id,
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "turn_number": turn_number,
                    "customer_id": customer_id,
                    "created_at": created_at,
                    "payload_json": payload_json,
                },
            )
            return turn_number

    def get_session_events(self, session_id: str) -> List[Dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT event_id, session_id, turn_id, turn_number, customer_id,
                           created_at, payload_json
                    FROM working_events
                    WHERE session_id = :session_id
                    ORDER BY turn_number
                    """
                ),
                {"session_id": session_id},
            ).mappings().all()
        return [
            {
                "event_id": row["event_id"],
                "session_id": row["session_id"],
                "turn_id": row["turn_id"],
                "turn_number": row["turn_number"],
                "customer_id": row["customer_id"],
                "created_at": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def save_episode(
        self,
        *,
        session_id: str,
        customer_id: Optional[str],
        ended_at: str,
        payload: Dict[str, Any],
    ) -> None:
        """Upsert the structured summary of a completed session."""
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO episodic_memory (
                        session_id, customer_id, ended_at, payload_json
                    ) VALUES (
                        :session_id, :customer_id, :ended_at, :payload_json
                    )
                    ON CONFLICT(session_id) DO UPDATE SET
                        customer_id = excluded.customer_id,
                        ended_at = excluded.ended_at,
                        payload_json = excluded.payload_json
                    """
                ),
                {
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "ended_at": ended_at,
                    "payload_json": json.dumps(
                        payload, ensure_ascii=False, separators=(",", ":")
                    ),
                },
            )

    def get_recent_episodes(
        self,
        customer_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT session_id, customer_id, ended_at, payload_json
                    FROM episodic_memory
                    WHERE customer_id = :customer_id
                    ORDER BY ended_at DESC
                    LIMIT :limit
                    """
                ),
                {"customer_id": customer_id, "limit": limit},
            ).mappings().all()
        return [
            {
                "session_id": row["session_id"],
                "customer_id": row["customer_id"],
                "ended_at": row["ended_at"],
                **json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def get_episode(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT session_id, customer_id, ended_at, payload_json
                    FROM episodic_memory
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "customer_id": row["customer_id"],
            "ended_at": row["ended_at"],
            **json.loads(row["payload_json"]),
        }

    def save_profile_facts(
        self,
        customer_id: str,
        facts: List[Dict[str, Any]],
        session_id: str,
        updated_at: str,
    ) -> None:
        with self.engine.begin() as connection:
            for fact in facts:
                connection.execute(
                    text(
                        """
                        INSERT INTO profile_facts (
                            customer_id, profile_key, profile_value_json,
                            provenance_session_id, updated_at
                        ) VALUES (
                            :customer_id, :profile_key, :profile_value_json,
                            :provenance_session_id, :updated_at
                        )
                        ON CONFLICT(customer_id, profile_key) DO UPDATE SET
                            profile_value_json = excluded.profile_value_json,
                            provenance_session_id = excluded.provenance_session_id,
                            updated_at = excluded.updated_at
                        """
                    ),
                    {
                        "customer_id": customer_id,
                        "profile_key": fact["key"],
                        "profile_value_json": json.dumps(
                            fact["value"],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        "provenance_session_id": session_id,
                        "updated_at": updated_at,
                    },
                )

    def get_profile_facts(self, customer_id: str) -> Dict[str, Any]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT profile_key, profile_value_json
                    FROM profile_facts
                    WHERE customer_id = :customer_id
                    """
                ),
                {"customer_id": customer_id},
            ).mappings().all()
        return {
            row["profile_key"]: json.loads(row["profile_value_json"])
            for row in rows
        }

    def close(self) -> None:
        self.engine.dispose()


_default_store: Optional[PostgresMemoryStore] = None
_default_store_lock = RLock()


def get_postgres_memory_store() -> PostgresMemoryStore:
    global _default_store
    if _default_store is None:
        with _default_store_lock:
            if _default_store is None:
                _default_store = PostgresMemoryStore()
    return _default_store


def close_postgres_memory_store() -> None:
    global _default_store
    with _default_store_lock:
        store = _default_store
        _default_store = None
    if store is not None:
        store.close()
