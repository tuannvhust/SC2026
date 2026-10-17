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


def checkpointer_database_url() -> str:
    """Prefer the Supavisor pooler for long-lived checkpointer pools.

    Direct ``db.<ref>.supabase.co:5432`` connections are frequently closed on
    idle IPv6 from Windows/dev machines (``pool-1`` errors on Turn 2+).
    ``SUPABASE_POOLER_URL`` is optional; falls back to ``default_database_url``.
    """
    pooler_url = os.getenv("SUPABASE_POOLER_URL", "").strip()
    if pooler_url:
        return pooler_url
    return default_database_url()


def describe_database_url(database_url: str) -> str:
    """Safe host/port/db summary for logs (never includes credentials)."""
    try:
        url = make_url(database_url)
        host = url.host or "unknown-host"
        port = url.port or "default-port"
        database = url.database or "unknown-db"
        query = dict(url.query)
        sslmode = query.get("sslmode", "unset")
        return f"{host}:{port}/{database} sslmode={sslmode}"
    except Exception:
        return "unparseable-database-url"


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
            pool_recycle=300,
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
        self.profile_fact_history = Table(
            "profile_fact_history",
            self.metadata,
            Column("history_id", Integer, primary_key=True, autoincrement=True),
            Column("customer_id", String, nullable=False),
            Column("profile_key", String, nullable=False),
            Column("old_value_json", String),
            Column("new_value_json", String, nullable=False),
            Column("provenance_session_id", String, nullable=False),
            Column("changed_at", String, nullable=False),
        )
        Index(
            "idx_profile_fact_history_customer",
            self.profile_fact_history.c.customer_id,
            self.profile_fact_history.c.profile_key,
            self.profile_fact_history.c.changed_at,
        )
        self.metadata.create_all(self.engine)

    def _ensure_profile_fact_history_table(self) -> None:
        """Create history table on existing DBs (minimal migration)."""
        self.profile_fact_history.create(self.engine, checkfirst=True)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "idx_profile_fact_history_customer ON profile_fact_history "
                    "(customer_id, profile_key, changed_at)"
                )
            )

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

    def update_session_customer_id(
        self, session_id: str, customer_id: str
    ) -> None:
        """Backfill a resolved customer ID across every turn in a session."""
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT event_id, payload_json FROM working_events
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().all()
            for row in rows:
                payload = json.loads(row["payload_json"])
                identity = payload.setdefault("identity", {})
                identity["customer_id"] = customer_id
                connection.execute(
                    text(
                        """
                        UPDATE working_events
                        SET customer_id = :customer_id, payload_json = :payload_json
                        WHERE event_id = :event_id
                        """
                    ),
                    {
                        "customer_id": customer_id,
                        "payload_json": json.dumps(
                            payload, ensure_ascii=False, separators=(",", ":")
                        ),
                        "event_id": row["event_id"],
                    },
                )

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
        self._ensure_profile_fact_history_table()
        with self.engine.begin() as connection:
            for fact in facts:
                key = fact["key"]
                new_value_json = json.dumps(
                    fact["value"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                old_row = connection.execute(
                    text(
                        """
                        SELECT profile_value_json FROM profile_facts
                        WHERE customer_id = :customer_id AND profile_key = :profile_key
                        """
                    ),
                    {"customer_id": customer_id, "profile_key": key},
                ).mappings().first()
                old_value_json = old_row["profile_value_json"] if old_row else None
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
                        "profile_key": key,
                        "profile_value_json": new_value_json,
                        "provenance_session_id": session_id,
                        "updated_at": updated_at,
                    },
                )
                if old_value_json != new_value_json:
                    connection.execute(
                        text(
                            """
                            INSERT INTO profile_fact_history (
                                customer_id, profile_key, old_value_json,
                                new_value_json, provenance_session_id, changed_at
                            ) VALUES (
                                :customer_id, :profile_key, :old_value_json,
                                :new_value_json, :provenance_session_id, :changed_at
                            )
                            """
                        ),
                        {
                            "customer_id": customer_id,
                            "profile_key": key,
                            "old_value_json": old_value_json,
                            "new_value_json": new_value_json,
                            "provenance_session_id": session_id,
                            "changed_at": updated_at,
                        },
                    )

    def get_profile_fact_history(
        self, customer_id: str, profile_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        self._ensure_profile_fact_history_table()
        query = (
            "SELECT customer_id, profile_key, old_value_json, new_value_json, "
            "provenance_session_id, changed_at FROM profile_fact_history "
            "WHERE customer_id = :customer_id"
        )
        params: Dict[str, Any] = {"customer_id": customer_id}
        if profile_key:
            query += " AND profile_key = :profile_key"
            params["profile_key"] = profile_key
        query += " ORDER BY changed_at"
        with self.engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()
        return [
            {
                "customer_id": row["customer_id"],
                "profile_key": row["profile_key"],
                "old_value": json.loads(row["old_value_json"])
                if row["old_value_json"] is not None
                else None,
                "new_value": json.loads(row["new_value_json"]),
                "provenance_session_id": row["provenance_session_id"],
                "changed_at": row["changed_at"],
            }
            for row in rows
        ]

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
