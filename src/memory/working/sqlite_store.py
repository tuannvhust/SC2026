"""SQLite persistence for per-turn events and completed call episodes."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


def default_memory_db_path() -> Path:
    configured_path = os.getenv("MEMORY_SQLITE_PATH")
    if configured_path:
        path = Path(configured_path)
        return path if path.is_absolute() else _project_root() / path
    return _project_root() / "data" / "memory" / "agent_memory.sqlite3"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


class SQLiteMemoryStore:
    """Persist working events and one structured episodic record per session."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path is not None else default_memory_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS working_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    customer_id TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE (session_id, turn_id),
                    UNIQUE (session_id, turn_number)
                );

                CREATE INDEX IF NOT EXISTS idx_working_events_customer
                    ON working_events (customer_id, created_at);

                CREATE TABLE IF NOT EXISTS episodic_memory (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    ended_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_episodic_memory_customer
                    ON episodic_memory (customer_id, ended_at);
                """
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
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT turn_number FROM working_events
                WHERE session_id = ? AND turn_id = ?
                """,
                (session_id, turn_id),
            ).fetchone()
            if existing:
                turn_number = int(existing["turn_number"])
                connection.execute(
                    """
                    UPDATE working_events
                    SET customer_id = ?, created_at = ?, payload_json = ?
                    WHERE session_id = ? AND turn_id = ?
                    """,
                    (customer_id, created_at, payload_json, session_id, turn_id),
                )
                return turn_number

            latest = connection.execute(
                "SELECT MAX(turn_number) AS turn_number FROM working_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            turn_number = int(latest["turn_number"] or 0) + 1
            connection.execute(
                """
                INSERT INTO working_events (
                    event_id, session_id, turn_id, turn_number, customer_id,
                    created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    turn_id,
                    turn_number,
                    customer_id,
                    created_at,
                    payload_json,
                ),
            )
            return turn_number

    def get_session_events(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, session_id, turn_id, turn_number, customer_id,
                       created_at, payload_json
                FROM working_events
                WHERE session_id = ?
                ORDER BY turn_number
                """,
                (session_id,),
            ).fetchall()
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
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO episodic_memory (session_id, customer_id, ended_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    ended_at = excluded.ended_at,
                    payload_json = excluded.payload_json
                """,
                (
                    session_id,
                    customer_id,
                    ended_at,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def get_recent_episodes(
        self,
        customer_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, customer_id, ended_at, payload_json
                FROM episodic_memory
                WHERE customer_id = ?
                ORDER BY ended_at DESC
                LIMIT ?
                """,
                (customer_id, limit),
            ).fetchall()
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
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, customer_id, ended_at, payload_json
                FROM episodic_memory
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "customer_id": row["customer_id"],
            "ended_at": row["ended_at"],
            **json.loads(row["payload_json"]),
        }
