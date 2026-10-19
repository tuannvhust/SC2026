"""Simplified schema regression tests (SQLite, no live writes)."""
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from src.memory.working.postgres_store import PostgresMemoryStore
from src.tools import tool_repository


def _sqlite_store():
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def attach_public(connection, _record):
        connection.execute("ATTACH DATABASE ':memory:' AS public")

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE public.conversation_sessions (session_id TEXT PRIMARY KEY, customer_id TEXT, channel TEXT, status TEXT DEFAULT 'active', last_activity_at TEXT)"))
        conn.execute(text("CREATE TABLE public.working_events (event_id TEXT PRIMARY KEY, session_id TEXT, turn_id TEXT, turn_number INTEGER, customer_id TEXT, created_at TEXT, payload_json TEXT)"))
        conn.execute(text("CREATE TABLE public.profile_facts (customer_id TEXT NOT NULL, profile_key TEXT NOT NULL, profile_value TEXT, source_session_id TEXT, source_event_id TEXT, source_kind TEXT DEFAULT 'customer_stated', confidence REAL, updated_at TEXT, PRIMARY KEY (customer_id, profile_key))"))
        conn.execute(text("CREATE TABLE public.episodic_memory (session_id TEXT PRIMARY KEY, customer_id TEXT, ended_at TEXT, payload_json TEXT, summary TEXT, current_need TEXT, outcome TEXT)"))
    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    store.engine = engine
    from sqlalchemy import MetaData

    store.metadata = MetaData()
    return store


def test_runtime_creates_no_tables_or_history():
    store = _sqlite_store()
    assert not hasattr(store, "profile_fact_history")
    try:
        store.get_profile_fact_history("C001")
        raise AssertionError("history API must be removed")
    except RuntimeError as error:
        assert "simplified schema" in str(error)


def test_profile_upsert_keeps_current_value_only(monkeypatch):
    store = _sqlite_store()
    store.save_profile_facts(customer_id="C001", facts=[{"key": "size", "value": "M"}], session_id="S1", updated_at="2026-10-19T00:00:00+00:00")
    store.save_profile_facts(customer_id="C001", facts=[{"key": "size", "value": "L"}], session_id="S2", updated_at="2026-10-19T01:00:00+00:00")
    facts = store.get_profile_facts("C001")
    assert facts == {"size": "L"}
    provenance = store.get_profile_facts_with_provenance("C001")
    assert provenance["size"]["source_session_id"] == "S2"


def test_no_legacy_table_queries_in_runtime():
    import pathlib

    runtime = (pathlib.Path("src/tools/tool_repository.py").read_text(encoding="utf-8") + pathlib.Path("src/memory/working/postgres_store.py").read_text(encoding="utf-8"))
    for legacy in ("customer_identities", "customer_addresses", "profile_fact_candidates", "INSERT INTO profile_fact_history", "FROM profile_fact_history"):
        assert legacy not in runtime
