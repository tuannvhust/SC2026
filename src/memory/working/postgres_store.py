"""SQLAlchemy persistence for working events, episodes, and profile facts."""

from __future__ import annotations

from datetime import datetime, timezone
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
    inspect,
    text,
)
from sqlalchemy.engine import Engine, make_url


import uuid


def _json_default(obj: Any) -> Any:
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (datetime, )):
        return obj.isoformat()
    if hasattr(obj, "dict") and callable(obj.dict):
        return obj.dict()
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return obj.model_dump()
    return str(obj)


def _dumps_json(value: Any, separators=(",", ":")) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=separators,
        default=_json_default,
    )


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value



def _bounded_limit(limit: int, default: int = 10) -> int:
    return max(1, min(int(limit or default), 1000))


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
        channel: str = "web_chat",
    ) -> int:
        """Append or idempotently update an event and return its turn number."""
        self.ensure_session(
            session_id=session_id,
            customer_id=customer_id,
            channel=channel,
        )
        payload_json = _dumps_json(payload)
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
                    SELECT turn_number, customer_id, payload_json FROM working_events
                    WHERE session_id = :session_id AND turn_id = :turn_id
                    """
                ),
                {"session_id": session_id, "turn_id": turn_id},
            ).mappings().first()
            if existing:
                turn_number = int(existing["turn_number"])
                event_customer_id = customer_id or existing["customer_id"]
                if not customer_id and existing["customer_id"]:
                    previous_payload = _decode_json(existing["payload_json"]) or {}
                    identity = previous_payload.setdefault("identity", {})
                    identity.setdefault("customer_id", existing["customer_id"])
                    payload_json = json.dumps(
                        previous_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
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
                        "customer_id": event_customer_id,
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

    def ensure_session(
        self,
        *,
        session_id: str,
        customer_id: Optional[str] = None,
        channel: str = "web_chat",
    ) -> Optional[str]:
        """Create the session row idempotently, preserving known ownership.

        A missing customer ID never clears a previously resolved customer. A
        conflicting non-null customer ID is rejected instead of reassigning a
        session.
        """
        if not session_id or not session_id.strip():
            raise ValueError(
                "session_id is required to create a conversation session."
            )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO conversation_sessions (
                        session_id, customer_id, channel
                    ) VALUES (
                        :session_id, :customer_id, :channel
                    )
                    ON CONFLICT(session_id) DO UPDATE SET
                        customer_id = COALESCE(
                            conversation_sessions.customer_id,
                            excluded.customer_id
                        )
                    """
                ),
                {
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "channel": channel or "web_chat",
                },
            )
            row = connection.execute(
                text(
                    """
                    SELECT customer_id FROM conversation_sessions
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().one()
            stored_customer_id = row["customer_id"]
            if (
                customer_id is not None
                and stored_customer_id is not None
                and customer_id != stored_customer_id
            ):
                raise RuntimeError(
                    "Session is already associated with a different customer."
                )
            return stored_customer_id

    def get_session_events(
        self,
        session_id: str,
        customer_id: Optional[str] = None,
        limit: int = 20,
        unassigned_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Read only a bounded tail of events from the requested session.

        When a customer is known, unassigned events from before identity
        resolution remain visible, but events assigned to another customer do
        not.
        """
        params: Dict[str, Any] = {
            "session_id": session_id,
            "limit": _bounded_limit(limit, default=20),
        }
        customer_filter = ""
        if customer_id:
            customer_filter = (
                " AND (customer_id = :customer_id OR customer_id IS NULL)"
            )
            params["customer_id"] = customer_id
        elif unassigned_only:
            customer_filter = " AND customer_id IS NULL"
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(f"""
                    SELECT event_id, session_id, turn_id, turn_number, customer_id,
                           created_at, payload_json
                    FROM (
                        SELECT event_id, session_id, turn_id, turn_number,
                               customer_id, created_at, payload_json
                        FROM working_events
                        WHERE session_id = :session_id{customer_filter}
                        ORDER BY turn_number DESC
                        LIMIT :limit
                    ) recent_events
                    ORDER BY turn_number
                """),
                params,
            ).mappings().all()
        return [
            {
                "event_id": row["event_id"],
                "session_id": row["session_id"],
                "turn_id": row["turn_id"],
                "turn_number": row["turn_number"],
                "customer_id": row["customer_id"],
                "created_at": row["created_at"],
                "payload": _decode_json(row["payload_json"]) or {},
            }
            for row in rows
        ]

    def get_session_customer_id(self, session_id: str) -> Optional[str]:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT customer_id FROM conversation_sessions
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
        return row["customer_id"] if row else None

    def update_session_customer_id(
        self, session_id: str, customer_id: str
    ) -> None:
        """Backfill a resolved customer ID across session and working events.

        Updates ``conversation_sessions.customer_id`` and every
        ``working_events.customer_id``/payload identity for the session in a
        single transaction so session and event state stay consistent.
        """
        updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as connection:
            # Update the session record (only this session, not others).
            result = connection.execute(
                text(
                    """
                    UPDATE conversation_sessions
                    SET customer_id = :customer_id, updated_at = :updated_at
                    WHERE session_id = :session_id
                      AND (customer_id IS NULL OR customer_id = :customer_id)
                    """
                ),
                {
                    "customer_id": customer_id,
                    "session_id": session_id,
                    "updated_at": updated_at,
                },
            )
            if result.rowcount == 0:
                existing = connection.execute(
                    text(
                        """
                        SELECT customer_id FROM conversation_sessions
                        WHERE session_id = :session_id
                        """
                    ),
                    {"session_id": session_id},
                ).mappings().first()
                if existing and existing["customer_id"] not in (None, customer_id):
                    raise RuntimeError(
                        "Session is already associated with a different customer."
                    )
            # Backfill every working event in this session.
            rows = connection.execute(
                text(
                    """
                    SELECT event_id, payload_json FROM working_events
                    WHERE session_id = :session_id
                      AND (customer_id = :customer_id OR customer_id IS NULL)
                    """
                ),
                {"session_id": session_id, "customer_id": customer_id},
            ).mappings().all()
            for row in rows:
                payload = _decode_json(row["payload_json"]) or {}
                identity = payload.setdefault("identity", {})
                identity["customer_id"] = customer_id
                connection.execute(
                    text(
                        """
                        UPDATE working_events
                        SET customer_id = :customer_id, payload_json = :payload_json
                        WHERE event_id = :event_id AND session_id = :session_id
                          AND (customer_id = :customer_id OR customer_id IS NULL)
                        """
                    ),
                    {
                        "customer_id": customer_id,
                        "payload_json": json.dumps(
                            payload, ensure_ascii=False, separators=(",", ":")
                        ),
                        "event_id": row["event_id"],
                        "session_id": session_id,
                    },
                )

    def save_call_brief(
        self,
        session_id: str,
        customer_id: Optional[str],
        call_brief: Dict[str, Any],
        updated_at: Optional[str] = None,
    ) -> int:
        """Persist one session's latest brief and atomically advance revision."""
        timestamp = updated_at or datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO conversation_sessions (
                        session_id, customer_id, call_brief_json,
                        call_brief_revision, call_brief_updated_at, updated_at
                    ) VALUES (
                        :session_id, :customer_id, :call_brief_json,
                        1, :updated_at, :updated_at
                    )
                    ON CONFLICT(session_id) DO UPDATE SET
                        customer_id = COALESCE(
                            excluded.customer_id,
                            conversation_sessions.customer_id
                        ),
                        call_brief_json = excluded.call_brief_json,
                        call_brief_revision =
                            conversation_sessions.call_brief_revision + 1,
                        call_brief_updated_at = excluded.call_brief_updated_at,
                        updated_at = excluded.updated_at
                    WHERE conversation_sessions.customer_id IS NULL
                       OR excluded.customer_id IS NULL
                       OR conversation_sessions.customer_id = excluded.customer_id
                    """
                ),
                {
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "call_brief_json": json.dumps(
                        call_brief, ensure_ascii=False, separators=(",", ":")
                    ),
                    "updated_at": timestamp,
                },
            )
            row = connection.execute(
                text(
                    """
                    SELECT call_brief_revision FROM conversation_sessions
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
            if result.rowcount == 0:
                raise RuntimeError(
                    "Call Brief was not saved because the session belongs "
                    "to a different customer."
                )
            if row is None:
                raise RuntimeError("Call Brief session row was not persisted.")
            return int(row["call_brief_revision"])

    def save_episode(
        self,
        *,
        session_id: str,
        customer_id: Optional[str],
        ended_at: str,
        payload: Dict[str, Any],
    ) -> None:
        """Upsert the structured summary of a completed session."""
        columns = {
            column["name"] for column in inspect(self.engine).get_columns("episodic_memory")
        }
        if "summary" in columns:
            values: Dict[str, Any] = {
                "session_id": session_id,
                "customer_id": customer_id,
                "ended_at": ended_at,
                "summary": str(payload.get("summary") or "Session completed."),
                "current_need": payload.get("current_need"),
                "outcome": payload.get("outcome"),
                "handoff_reason": payload.get("handoff_reason"),
                "products_advised": json.dumps(
                    payload.get("products_advised", []), ensure_ascii=False
                ),
                "orders_summary": json.dumps(
                    payload.get("orders", []), ensure_ascii=False
                ),
                "open_questions": json.dumps(
                    payload.get("open_questions", []), ensure_ascii=False
                ),
                "open_blockers": json.dumps(
                    payload.get("open_blockers", []), ensure_ascii=False
                ),
                "next_actions": json.dumps(
                    payload.get("next_actions", []), ensure_ascii=False
                ),
                "turn_count": int(payload.get("turn_count") or 0),
            }
            if "payload_json" in columns:
                values["payload_json"] = _dumps_json(payload)
            names = [name for name in values if name in columns]
            insert_columns = ", ".join(names)
            bind_names = ", ".join(f":{name}" for name in names)
            updates = ", ".join(
                f"{name} = excluded.{name}"
                for name in names
                if name != "session_id"
            )
            statement = (
                f"INSERT INTO episodic_memory ({insert_columns}) "
                f"VALUES ({bind_names}) ON CONFLICT(session_id) DO UPDATE SET {updates}"
            )
        else:
            values = {
                "session_id": session_id,
                "customer_id": customer_id,
                "ended_at": ended_at,
                "payload_json": _dumps_json(payload),
            }
            statement = """
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

        with self.engine.begin() as connection:
            connection.execute(text(statement), values)

    def get_recent_episodes(
        self,
        customer_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        columns = {
            column["name"] for column in inspect(self.engine).get_columns("episodic_memory")
        }
        available = [
            name
            for name in (
                "session_id",
                "customer_id",
                "ended_at",
                "payload_json",
                "summary",
                "current_need",
                "outcome",
                "handoff_reason",
                "products_advised",
                "orders_summary",
                "open_questions",
                "open_blockers",
                "next_actions",
            )
            if name in columns
        ]
        if not {"session_id", "customer_id", "ended_at"}.issubset(columns):
            raise RuntimeError("episodic_memory is missing required columns.")
        selected_columns = ", ".join(available)
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT {selected_columns}
                    FROM episodic_memory
                    WHERE customer_id = :customer_id
                    ORDER BY ended_at DESC
                    LIMIT :limit
                    """
                ),
                {"customer_id": customer_id, "limit": _bounded_limit(limit)},
            ).mappings().all()
        episodes = []
        json_columns = {
            "payload_json",
            "products_advised",
            "orders_summary",
            "open_questions",
            "open_blockers",
            "next_actions",
        }
        for row in rows:
            payload = _decode_json(row.get("payload_json")) or {}
            if not isinstance(payload, dict):
                payload = {}
            episode = {**payload}
            for name in available:
                if name == "payload_json":
                    continue
                value = row[name]
                if name in json_columns and value is not None:
                    value = _decode_json(value)
                episode[name] = value
            episodes.append(episode)
        return episodes

    def get_profile_facts_with_provenance(
        self, customer_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """Return committed profile facts with the source metadata available."""
        columns = {
            column["name"] for column in inspect(self.engine).get_columns("profile_facts")
        }
        value_column = (
            "profile_value_json"
            if "profile_value_json" in columns
            else "profile_value"
            if "profile_value" in columns
            else None
        )
        source_column = (
            "provenance_session_id"
            if "provenance_session_id" in columns
            else "source_session_id"
            if "source_session_id" in columns
            else None
        )
        if value_column is None or "profile_key" not in columns:
            raise RuntimeError("profile_facts is missing required columns.")
        selected = ["profile_key", value_column]
        if source_column:
            selected.append(source_column)
        if "updated_at" in columns:
            selected.append("updated_at")
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT {", ".join(selected)}
                    FROM profile_facts
                    WHERE customer_id = :customer_id
                    """
                ),
                {"customer_id": customer_id},
            ).mappings().all()
        facts = {}
        for row in rows:
            facts[row["profile_key"]] = {
                "value": _decode_json(row[value_column]),
                "source_session_id": row[source_column] if source_column else None,
                "updated_at": row["updated_at"] if "updated_at" in row else None,
            }
        return facts

    def get_profile_facts(self, customer_id: str) -> Dict[str, Any]:
        return {
            key: fact["value"]
            for key, fact in self.get_profile_facts_with_provenance(
                customer_id
            ).items()
        }

    def get_episode(self, session_id: str) -> Optional[Dict[str, Any]]:
        episodes = self.get_recent_episodes_for_session(session_id)
        return episodes

    def get_recent_episodes_for_session(
        self, session_id: str
    ) -> Optional[Dict[str, Any]]:
        columns = {
            column["name"] for column in inspect(self.engine).get_columns("episodic_memory")
        }
        available = [
            name
            for name in (
                "session_id",
                "customer_id",
                "ended_at",
                "payload_json",
                "summary",
                "current_need",
                "outcome",
                "handoff_reason",
                "products_advised",
                "orders_summary",
                "open_questions",
                "open_blockers",
                "next_actions",
            )
            if name in columns
        ]
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    f"""
                    SELECT {", ".join(available)}
                    FROM episodic_memory
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).mappings().first()
        if row is None:
            return None
        payload = _decode_json(row.get("payload_json")) or {}
        episode = dict(payload) if isinstance(payload, dict) else {}
        json_columns = {
            "products_advised",
            "orders_summary",
            "open_questions",
            "open_blockers",
            "next_actions",
        }
        for name in available:
            if name == "payload_json":
                continue
            value = row[name]
            if name in json_columns and value is not None:
                value = _decode_json(value)
            episode[name] = value
        return episode

    def save_profile_facts(
        self,
        customer_id: str,
        facts: List[Dict[str, Any]],
        session_id: str,
        updated_at: str,
    ) -> None:
        self._ensure_profile_fact_history_table()
        columns = {
            column["name"] for column in inspect(self.engine).get_columns("profile_facts")
        }
        value_column = (
            "profile_value_json"
            if "profile_value_json" in columns
            else "profile_value"
        )
        source_column = (
            "provenance_session_id"
            if "provenance_session_id" in columns
            else "source_session_id"
        )
        history_columns = {
            column["name"]
            for column in inspect(self.engine).get_columns("profile_fact_history")
        }
        with self.engine.begin() as connection:
            for fact in facts:
                key = fact["key"]
                new_value_json = json.dumps(
                    fact["value"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                old_row = connection.execute(
                    text(f"""
                        SELECT {value_column} FROM profile_facts
                        WHERE customer_id = :customer_id AND profile_key = :profile_key
                    """),
                    {"customer_id": customer_id, "profile_key": key},
                ).mappings().first()
                old_value_json = old_row[value_column] if old_row else None
                fact_values = {
                    "customer_id": customer_id,
                    "profile_key": key,
                    "value_json": new_value_json,
                    "source_session_id": session_id,
                    "updated_at": updated_at,
                }
                connection.execute(
                    text(f"""
                        INSERT INTO profile_facts (
                            customer_id, profile_key, {value_column},
                            {source_column}, updated_at
                        ) VALUES (
                            :customer_id, :profile_key, :value_json,
                            :source_session_id, :updated_at
                        )
                        ON CONFLICT(customer_id, profile_key) DO UPDATE SET
                            {value_column} = excluded.{value_column},
                            {source_column} = excluded.{source_column},
                            updated_at = excluded.updated_at
                    """),
                    fact_values,
                )
                if _decode_json(old_value_json) != _decode_json(new_value_json):
                    if "old_value_json" in history_columns:
                        history_names = (
                            "customer_id, profile_key, old_value_json, "
                            "new_value_json, provenance_session_id, changed_at"
                        )
                        history_values = (
                            ":customer_id, :profile_key, :old_value, "
                            ":new_value, :source_session_id, :changed_at"
                        )
                        history_params = {
                            **fact_values,
                            "old_value": old_value_json,
                            "new_value": new_value_json,
                            "provenance_session_id": session_id,
                            "changed_at": updated_at,
                        }
                    else:
                        history_names = (
                            "customer_id, profile_key, old_value, new_value, "
                            "change_type, source_session_id, changed_at"
                        )
                        history_values = (
                            ":customer_id, :profile_key, :old_value, :new_value, "
                            ":change_type, :source_session_id, :changed_at"
                        )
                        history_params = {
                            **fact_values,
                            "old_value": old_value_json,
                            "new_value": new_value_json,
                            "change_type": "created" if old_row is None else "updated",
                            "changed_at": updated_at,
                        }
                    connection.execute(
                        text(
                            f"INSERT INTO profile_fact_history ({history_names}) "
                            f"VALUES ({history_values})"
                        ),
                        history_params,
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
