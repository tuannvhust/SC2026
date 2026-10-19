import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine, event, text

from src.api.routers import graph_runner
from src.graph.builder import build_graph
from src.graph.nodes import persistence_nodes
from src.memory.working.postgres_store import PostgresMemoryStore


def _create_store(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'session-lifecycle.sqlite3'}"
    bootstrap = create_engine(database_url)
    with bootstrap.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    channel TEXT NOT NULL DEFAULT 'web_chat',
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at TEXT
                )
                """
            )
        )
    bootstrap.dispose()

    store = PostgresMemoryStore(database_url)

    @event.listens_for(store.engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    store.engine.dispose()
    with store.engine.begin() as connection:
        connection.execute(text("DROP TABLE working_events"))
        connection.execute(
            text(
                """
                CREATE TABLE working_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL
                        REFERENCES conversation_sessions(session_id),
                    turn_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    customer_id TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(session_id, turn_id),
                    UNIQUE(session_id, turn_number)
                )
                """
            )
        )
    return store


def _session_row(store, session_id):
    with store.engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT session_id, customer_id, channel
                FROM conversation_sessions WHERE session_id = :session_id
                """
            ),
            {"session_id": session_id},
        ).mappings().first()


def test_new_session_exists_before_working_event_insert(tmp_path):
    store = _create_store(tmp_path)
    try:
        turn_number = store.append_turn(
            event_id="EVENT-1",
            session_id="SESSION-NEW",
            turn_id="TURN-1",
            customer_id=None,
            created_at="2026-10-18T00:00:00+00:00",
            payload={"identity": {}},
        )

        assert turn_number == 1
        assert _session_row(store, "SESSION-NEW")["customer_id"] is None
        assert store.get_session_events("SESSION-NEW")[0]["event_id"] == "EVENT-1"
    finally:
        store.close()


def test_existing_session_is_reused_without_duplicate_and_null_never_clears_owner(
    tmp_path,
):
    store = _create_store(tmp_path)
    try:
        assert (
            store.ensure_session(
                session_id="SESSION-EXISTING",
                customer_id="CUST-1",
                channel="hotline",
            )
            == "CUST-1"
        )
        assert (
            store.ensure_session(
                session_id="SESSION-EXISTING",
                customer_id=None,
                channel="web_chat",
            )
            == "CUST-1"
        )
        with store.engine.connect() as connection:
            count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM conversation_sessions "
                    "WHERE session_id = 'SESSION-EXISTING'"
                )
            ).scalar_one()

        row = _session_row(store, "SESSION-EXISTING")
        assert count == 1
        assert row["customer_id"] == "CUST-1"
        assert row["channel"] == "hotline"
    finally:
        store.close()


def test_unknown_customer_session_still_persists_null_customer_event(tmp_path):
    store = _create_store(tmp_path)
    try:
        store.ensure_session(
            session_id="SESSION-GUEST",
            customer_id=None,
            channel="web_chat",
        )
        turn_number = store.append_turn(
            event_id="EVENT-GUEST",
            session_id="SESSION-GUEST",
            turn_id="TURN-GUEST",
            customer_id=None,
            created_at="2026-10-18T00:00:00+00:00",
            payload={"identity": {}, "status": {"needs_identity": True}},
        )

        assert turn_number == 1
        assert _session_row(store, "SESSION-GUEST")["customer_id"] is None
        assert store.get_session_events("SESSION-GUEST")[0]["customer_id"] is None
    finally:
        store.close()


def test_api_creates_new_session_before_graph_starts(tmp_path, monkeypatch):
    store = _create_store(tmp_path)
    graph_observations = []

    def stream(state, _config, stream_mode=None):
        graph_observations.append(_session_row(store, state["session_id"]))
        yield ("values", {**state, "messages": [*state["messages"], AIMessage(content="Hi.")]})

    monkeypatch.setattr(graph_runner, "get_postgres_memory_store", lambda: store)
    monkeypatch.setattr(
        graph_runner,
        "graph",
        SimpleNamespace(checkpointer_enabled=False, stream=stream),
    )
    try:
        result = graph_runner.invoke_customer_turn(
            customer_id=None,
            session_id="SESSION-API-NEW",
            turn_id="TURN-API-NEW",
            message="Hello",
            channel="chat",
        )

        assert result["session_id"] == "SESSION-API-NEW"
        assert len(graph_observations) == 1
        assert graph_observations[0]["session_id"] == "SESSION-API-NEW"
        assert graph_observations[0]["customer_id"] is None
        assert graph_observations[0]["channel"] == "web_chat"
    finally:
        store.close()


def test_continue_session_preserves_session_id_and_customer_id(tmp_path, monkeypatch):
    store = _create_store(tmp_path)
    store.ensure_session(
        session_id="SESSION-CONTINUE",
        customer_id="CUST-1",
        channel="hotline",
    )
    store.append_turn(
        event_id="EVENT-OLD",
        session_id="SESSION-CONTINUE",
        turn_id="TURN-OLD",
        customer_id="CUST-1",
        created_at="2026-10-17T00:00:00+00:00",
        payload={"messages": []},
    )
    observed = {}

    def stream(state, _config, stream_mode=None):
        observed["state"] = state
        observed["stream_mode"] = stream_mode
        yield (
            "values",
            {
                **state,
                "messages": [*state["messages"], AIMessage(content="Continued.")],
            },
        )

    monkeypatch.setattr(graph_runner, "get_postgres_memory_store", lambda: store)
    monkeypatch.setattr(
        graph_runner,
        "graph",
        SimpleNamespace(checkpointer_enabled=False, stream=stream),
    )
    try:
        result = graph_runner.invoke_customer_turn(
            customer_id=None,
            session_id="SESSION-CONTINUE",
            turn_id="TURN-NEW",
            message="Continue",
            channel="chat",
        )

        assert result["session_id"] == "SESSION-CONTINUE"
        assert observed["state"]["session_id"] == "SESSION-CONTINUE"
        assert observed["state"]["customer_id"] == "CUST-1"
        assert _session_row(store, "SESSION-CONTINUE")["customer_id"] == "CUST-1"
        assert observed["stream_mode"] == ["values", "debug"]
    finally:
        store.close()


def test_session_creation_failure_stops_before_events_or_graph(monkeypatch):
    calls = []

    class FailingStore:
        def ensure_session(self, **_kwargs):
            raise OSError("database unavailable")

        def get_session_events(self, *_args, **_kwargs):
            calls.append("events")
            return []

    def fail_if_graph_runs(*_args, **_kwargs):
        calls.append("graph")
        raise AssertionError("graph must not run if session creation fails")

    monkeypatch.setattr(
        graph_runner, "get_postgres_memory_store", lambda: FailingStore()
    )
    monkeypatch.setattr(
        graph_runner,
        "graph",
        SimpleNamespace(checkpointer_enabled=False, stream=fail_if_graph_runs),
    )

    with pytest.raises(RuntimeError, match="create or confirm"):
        graph_runner.invoke_customer_turn(
            customer_id=None,
            session_id="SESSION-FAIL",
            turn_id="TURN-FAIL",
            message="Hello",
            channel="chat",
        )

    assert calls == []


def test_identity_then_request_then_persist_creates_unknown_session(tmp_path, monkeypatch):
    store = _create_store(tmp_path)
    monkeypatch.setattr(
        persistence_nodes, "get_working_memory_store", lambda: store
    )
    try:
        result = build_graph().invoke(
            {
                "messages": [HumanMessage(content="I need help with a product")],
                "session_id": "SESSION-IDENTITY",
                "turn_id": "TURN-IDENTITY",
            }
        )

        session = _session_row(store, "SESSION-IDENTITY")
        events = store.get_session_events("SESSION-IDENTITY")
        assert result["identity_status"] == "needs_input"
        assert session["session_id"] == result["session_id"] == "SESSION-IDENTITY"
        assert session["customer_id"] is None
        assert len(events) == 1
        assert events[0]["turn_id"] == "TURN-IDENTITY"
        assert events[0]["customer_id"] is None
        assert json.loads(json.dumps(events[0]["payload"]))["identity"][
            "needs_identity"
        ] is True
    finally:
        store.close()
