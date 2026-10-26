from sqlalchemy.engine import make_url

from src.memory.working.postgres_store import (
    PostgresMemoryStore,
    _normalized_database_url,
    default_database_url,
)


def test_supabase_url_uses_psycopg2_and_requires_tls():
    url = _normalized_database_url(
        "postgresql://user:password@db.example.supabase.co:5432/postgres"
    )

    assert url.drivername == "postgresql+psycopg2"
    assert url.query["sslmode"] == "require"


def test_database_url_comes_from_supabase_or_standard_environment(monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://db.example/agent")
    assert default_database_url() == "postgresql://db.example/agent"

    monkeypatch.setenv("SUPABASE_DATABASE_URL", "postgresql://supabase/agent")
    assert default_database_url() == "postgresql://supabase/agent"


def test_profile_facts_are_upserted_and_read_as_json():
    from sqlalchemy import create_engine, text

    database_url = "sqlite+pysqlite:///:memory:"
    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    from sqlalchemy import MetaData

    store.engine = create_engine(database_url)
    store.metadata = MetaData()
    with store.engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    channel TEXT,
                    last_activity_at TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE profile_facts (
                    customer_id TEXT NOT NULL,
                    profile_key TEXT NOT NULL,
                    profile_value TEXT,
                    source_session_id TEXT,
                    source_event_id TEXT,
                    source_kind TEXT DEFAULT 'customer_stated',
                    confidence REAL,
                    updated_at TEXT,
                    PRIMARY KEY (customer_id, profile_key)
                )
                """
            )
        )
        connection.execute(
            text("INSERT INTO conversation_sessions (session_id, customer_id) VALUES ('session-1', 'customer-1'), ('session-2', 'customer-1')")
        )
    try:
        store.save_profile_facts(
            "customer-1",
            [{"key": "preferred_category", "value": {"name": "air purifier"}}],
            "session-1",
            "2026-10-09T00:00:00+00:00",
        )
        store.save_profile_facts(
            "customer-1",
            [{"key": "preferred_category", "value": "home appliance"}],
            "session-2",
            "2026-10-09T00:01:00+00:00",
        )

        assert store.get_profile_facts("customer-1") == {
            "preferred_category": "home appliance"
        }
        assert store.get_profile_facts("another-customer") == {}
    finally:
        store.close()
