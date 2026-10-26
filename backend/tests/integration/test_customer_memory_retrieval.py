import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient

from src.api.main import app
from src.graph.nodes import input_nodes
from src.graph.nodes.input_nodes import build_call_brief_node, resolve_identity_node
from src.memory.working.postgres_store import PostgresMemoryStore


def _create_v1_store(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'memory-v1.sqlite3'}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    call_brief_json TEXT,
                    call_brief_revision INTEGER NOT NULL DEFAULT 0,
                    call_brief_updated_at TEXT,
                    updated_at TEXT
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
                    profile_value TEXT NOT NULL,
                    source_session_id TEXT,
                    source_kind TEXT NOT NULL DEFAULT 'customer_stated',
                    confidence REAL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (customer_id, profile_key)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE profile_fact_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    profile_key TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    change_type TEXT NOT NULL,
                    source_session_id TEXT,
                    changed_at TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE profile_fact_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    profile_key TEXT NOT NULL,
                    proposed_value TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE episodic_memory (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    summary TEXT NOT NULL,
                    current_need TEXT,
                    outcome TEXT,
                    handoff_reason TEXT,
                    products_advised TEXT NOT NULL DEFAULT '[]',
                    orders_summary TEXT NOT NULL DEFAULT '[]',
                    open_questions TEXT NOT NULL DEFAULT '[]',
                    open_blockers TEXT NOT NULL DEFAULT '[]',
                    next_actions TEXT NOT NULL DEFAULT '[]',
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    ended_at TEXT NOT NULL,
                    payload_json TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE working_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    customer_id TEXT,
                    event_type TEXT NOT NULL DEFAULT 'turn_saved',
                    event_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text("INSERT INTO conversation_sessions (session_id, customer_id) VALUES ('SESSION-1', 'CUST-1')")
        )
    engine.dispose()
    return PostgresMemoryStore(database_url)


def _seed_customer_memory(store):
    with store.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO profile_facts
                    (customer_id, profile_key, profile_value, source_session_id, updated_at)
                VALUES
                    ('CUST-1', 'preferred_category', '"air purifier"', 'OLD-1', '2026-10-01'),
                    ('CUST-1', 'room_size_m2', '{"value": 20, "unit": "m2"}', 'OLD-1', '2026-10-01'),
                    ('CUST-2', 'preferred_category', '"laptop"', 'OLD-2', '2026-10-02')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO profile_fact_candidates
                    (candidate_id, customer_id, profile_key, proposed_value, status)
                VALUES ('CANDIDATE-1', 'CUST-1', 'budget', '"unconfirmed"', 'pending')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO episodic_memory
                    (session_id, customer_id, summary, current_need, outcome,
                     products_advised, orders_summary, open_questions,
                     open_blockers, next_actions, turn_count, ended_at, payload_json)
                VALUES
                    (:session_id, :customer_id, :summary, :current_need, :outcome,
                     :products, '[]', :questions, :blockers, :next_actions,
                     2, :ended_at, :payload)
                """
            ),
            {
                "session_id": "OLD-1",
                "customer_id": "CUST-1",
                "summary": "Historical quote: 4,500,000 VND with promo OLD10.",
                "current_need": "Máy lọc cho phòng ngủ",
                "outcome": "pending",
                "products": json.dumps(
                    [
                        {
                            "sku": "SKU-AP-X",
                            "name": "AirPure X",
                            "price_quoted_vnd": 4_500_000,
                            "promo_code": "OLD10",
                            "in_stock": True,
                        }
                    ]
                ),
                "questions": json.dumps(["Diện tích phòng bao nhiêu?"]),
                "blockers": json.dumps(["Chưa rõ diện tích phòng"]),
                "next_actions": json.dumps(["Xác nhận diện tích phòng"]),
                "ended_at": "2026-10-10T00:00:00+00:00",
                "payload": json.dumps({"summary_source": "episode"}),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO episodic_memory
                    (session_id, customer_id, summary, outcome, turn_count,
                     ended_at, payload_json)
                VALUES
                    ('OLD-2', 'CUST-2', 'Private memory for customer two.',
                     'completed', 1, '2026-10-11T00:00:00+00:00', '{}')
                """
            )
        )


def _brief_state(customer_id="CUST-1", session_id="NEW-1"):
    return {
        "messages": [HumanMessage(content="Tôi muốn tiếp tục tư vấn")],
        "customer_id": customer_id,
        "customer_info": {
            "name": "Lan",
            "phone": "0901234567",
            "_input_text": "Tôi muốn tiếp tục tư vấn",
        },
        "session_id": session_id,
    }


def test_call_brief_restores_committed_facts_and_recent_episode(tmp_path, monkeypatch):
    store = _create_v1_store(tmp_path)
    _seed_customer_memory(store)
    monkeypatch.setattr(input_nodes, "get_postgres_memory_store", lambda: store)
    # Use the real profile adapter with the isolated SQL store.
    from src.memory.profile.profile_store import ProfileStore

    monkeypatch.setattr(
        input_nodes, "get_profile_store", lambda: ProfileStore(postgres_store=store)
    )
    try:
        result = build_call_brief_node(_brief_state())
        brief = result["call_brief"]
        assert brief["profile_facts"]["preferred_category"] == "air purifier"
        assert brief["profile_facts"]["room_size_m2"] == {
            "value": 20,
            "unit": "m2",
        }
        assert "budget" not in brief["profile_facts"]
        assert "laptop" not in str(brief["profile_facts"])
        assert brief["recent_sessions"][0]["session_id"] == "OLD-1"
        assert "Historical" in brief["recent_sessions"][0]["summary"]
        assert brief["open_blockers"] == ["Chưa rõ diện tích phòng"]
        assert brief["open_questions"] == ["Diện tích phòng bao nhiêu?"]
        assert brief["suggested_next_action"].startswith(
            "Confirm whether this previous blocker remains"
        )
        assert brief["memory_status"] == "loaded"
        assert brief["memory_sources"]["profile_facts"]["preferred_category"][
            "session_id"
        ] == "OLD-1"
        assert brief["products_advised"] == [{"sku": "SKU-AP-X", "name": "AirPure X"}]
        assert brief["stale_warnings"]
        assert "price_quoted_vnd" not in str(brief["products_advised"])
        assert "OLD10" not in str(brief["products_advised"])
    finally:
        store.close()


def test_customer_without_history_gets_valid_empty_brief(tmp_path, monkeypatch):
    store = _create_v1_store(tmp_path)
    monkeypatch.setattr(input_nodes, "get_postgres_memory_store", lambda: store)
    from src.memory.profile.profile_store import ProfileStore

    monkeypatch.setattr(
        input_nodes, "get_profile_store", lambda: ProfileStore(postgres_store=store)
    )
    try:
        brief = build_call_brief_node(_brief_state("CUST-EMPTY"))["call_brief"]
        assert brief["memory_status"] == "empty"
        assert brief["profile_facts"] == {}
        assert brief["recent_sessions"] == []
        assert brief["open_blockers"] == []
        assert brief["open_questions"] == []
        assert brief["suggested_next_action"]
    finally:
        store.close()


def test_newly_resolved_session_loads_memory_before_planning(tmp_path, monkeypatch):
    store = _create_v1_store(tmp_path)
    with store.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO conversation_sessions (session_id, customer_id) VALUES ('SESSION-NEW', NULL)")
        )
    _seed_customer_memory(store)
    monkeypatch.setattr(input_nodes, "get_postgres_memory_store", lambda: store)
    from src.memory.profile.profile_store import ProfileStore

    monkeypatch.setattr(
        input_nodes, "get_profile_store", lambda: ProfileStore(postgres_store=store)
    )
    monkeypatch.setattr(
        input_nodes,
        "crm_get_customer",
        type(
            "FakeCRM",
            (),
            {
                "invoke": staticmethod(
                    lambda _payload: {
                        "found": True,
                        "customer_id": "CUST-1",
                        "name": "Lan",
                        "honorific": None,
                        "phone": "0901234567",
                        "is_verified": True,
                        "ambiguous": False,
                        "error": None,
                    }
                )
            },
        )(),
    )
    from src.graph.builder import route_after_call_brief, route_after_identity

    try:
        initial = {
            "messages": [HumanMessage(content="Tôi muốn tiếp tục tư vấn")],
            "customer_info": {
                "phone": "0901234567",
                "name": "Lan",
                "_input_text": "Tôi muốn tiếp tục tư vấn",
            },
            "session_id": "SESSION-NEW",
        }
        resolved = resolve_identity_node(initial)
        assert resolved["customer_id"] == "CUST-1"
        resolved_state = {**initial, **resolved}
        assert route_after_identity(resolved_state) == "build_call_brief"
        brief_result = build_call_brief_node(resolved_state)
        brief = brief_result["call_brief"]
        assert route_after_call_brief({**resolved_state, **brief_result}) == "plan_step"

        assert brief["recent_sessions"][0]["session_id"] == "OLD-1"
        assert brief["profile_facts"]["preferred_category"] == "air purifier"
        with store.engine.connect() as connection:
            session = connection.execute(
                text(
                    """
                    SELECT customer_id, call_brief_json, call_brief_revision
                    FROM conversation_sessions WHERE session_id = 'NEW-SESSION'
                    """
                )
            ).mappings().one()
        assert session["customer_id"] == "CUST-1"
        assert json.loads(session["call_brief_json"])["recent_sessions"][0][
            "session_id"
        ] == "OLD-1"
        assert session["call_brief_revision"] == 1
    finally:
        store.close()


def test_memory_query_failure_is_reported_not_as_empty_success(tmp_path, monkeypatch):
    store = _create_v1_store(tmp_path)
    monkeypatch.setattr(input_nodes, "get_postgres_memory_store", lambda: store)
    from src.memory.profile.profile_store import ProfileStore

    profile_store = ProfileStore(postgres_store=store)

    def fail_profile(_customer_id):
        raise RuntimeError("database unavailable")

    def fail_episodes(_customer_id, limit=10):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        profile_store, "get_profile_facts_with_provenance", fail_profile
    )
    monkeypatch.setattr(input_nodes, "get_profile_store", lambda: profile_store)
    monkeypatch.setattr(store, "get_recent_episodes", fail_episodes)
    try:
        brief = build_call_brief_node(_brief_state())["call_brief"]
        assert brief["memory_status"] == "error"
        assert brief["profile_facts"] == {}
        assert brief["recent_sessions"] == []
    finally:
        store.close()


def test_v1_fact_and_episode_writes_match_existing_columns(tmp_path):
    store = _create_v1_store(tmp_path)
    try:
        store.save_profile_facts(
            "CUST-1",
            [{"key": "preferred_category", "value": {"category": "appliance"}}],
            "SESSION-1",
            "2026-10-18T00:00:00+00:00",
        )
        store.save_episode(
            session_id="SESSION-1",
            customer_id="CUST-1",
            ended_at="2026-10-18T00:00:00+00:00",
            payload={
                "summary": "Session summary",
                "current_need": "Air purifier",
                "outcome": "completed",
                "products_advised": [{"sku": "SKU-1"}],
                "open_questions": ["Room size?"],
                "open_blockers": ["Awaiting room size"],
                "next_actions": ["Confirm room size"],
                "turn_count": 2,
            },
        )

        assert store.get_profile_facts("CUST-1") == {
            "preferred_category": {"category": "appliance"}
        }
        episode = store.get_episode("SESSION-1")
        assert episode["summary"] == "Session summary"
        assert episode["current_need"] == "Air purifier"
        assert episode["products_advised"] == [{"sku": "SKU-1"}]
        assert episode["next_actions"] == ["Confirm room size"]
    finally:
        store.close()


def test_session_events_are_bounded_and_customer_scoped(tmp_path):
    store = _create_v1_store(tmp_path)
    try:
        with store.engine.begin() as connection:
            for number, customer_id, session_id in (
                (1, "CUST-1", "SESSION-1"),
                (2, "CUST-2", "SESSION-1"),
                (3, None, "SESSION-1"),
                (4, "CUST-1", "SESSION-2"),
            ):
                connection.execute(
                    text(
                        """
                        INSERT INTO working_events
                            (event_id, session_id, turn_id, turn_number,
                             customer_id, created_at, payload_json)
                        VALUES
                            (:event_id, :session_id, :turn_id, :turn_number,
                             :customer_id, :created_at, :payload)
                        """
                    ),
                    {
                        "event_id": f"EV-{number}",
                        "session_id": session_id,
                        "turn_id": f"TURN-{number}",
                        "turn_number": number,
                        "customer_id": customer_id,
                        "created_at": "2026-10-18T00:00:00",
                        "payload": json.dumps({"number": number}),
                    },
                )

        rows = store.get_session_events(
            "SESSION-1", customer_id="CUST-1", limit=1
        )
        assert [(row["event_id"], row["customer_id"]) for row in rows] == [
            ("EV-3", None)
        ]
        assert all(row["session_id"] == "SESSION-1" for row in rows)
    finally:
        store.close()


def test_call_brief_revision_is_atomic_and_session_scoped(tmp_path):
    store = _create_v1_store(tmp_path)
    try:
        first_revision = store.save_call_brief(
            "SESSION-1", "CUST-1", {"current_need": "First"}
        )
        second_revision = store.save_call_brief(
            "SESSION-1", "CUST-1", {"current_need": "Updated"}
        )
        other_revision = store.save_call_brief(
            "SESSION-2", "CUST-2", {"current_need": "Other"}
        )
        assert (first_revision, second_revision, other_revision) == (1, 2, 1)

        with pytest.raises(RuntimeError, match="different customer"):
            store.save_call_brief(
                "SESSION-1", "CUST-2", {"current_need": "Must not overwrite"}
            )
        with store.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT session_id, customer_id, call_brief_json,
                           call_brief_revision
                    FROM conversation_sessions ORDER BY session_id
                    """
                )
            ).mappings().all()
        assert rows[0]["session_id"] == "SESSION-1"
        assert rows[0]["customer_id"] == "CUST-1"
        assert rows[0]["call_brief_revision"] == 2
        assert json.loads(rows[0]["call_brief_json"]) == {
            "current_need": "Updated"
        }
        assert rows[1]["session_id"] == "SESSION-2"
        assert rows[1]["customer_id"] == "CUST-2"
        assert rows[1]["call_brief_revision"] == 1
    finally:
        store.close()


def test_stream_sends_safe_call_brief_event_and_compatible_response(monkeypatch):
    from src.api.routers import chat

    internal_brief = {
        "memory_status": "loaded",
        "memory_sources": {"profile_facts": {"phone": {"session_id": "S-OLD"}}},
        "profile_facts": {"phone": "0901234567"},
        "customer_phone": "0901234567",
        "current_need": "Tiếp tục tư vấn",
        "recent_sessions": [
            {
                "date": "2026-10-10",
                "summary": "Đã trao đổi về sản phẩm.",
                "outcome": "pending",
            }
        ],
        "open_blockers": ["Xác nhận diện tích phòng"],
        "open_questions": [],
        "suggested_next_action": "Xác nhận diện tích phòng",
    }

    def invoke(**kwargs):
        kwargs["on_call_brief"](internal_brief)
        return {
            "messages": [AIMessage(content="Em tiếp tục hỗ trợ ạ.")],
            "session_id": kwargs["session_id"],
            "turn_id": kwargs["turn_id"],
            "call_brief": internal_brief,
        }

    monkeypatch.setattr(chat, "invoke_customer_turn", invoke)
    response = TestClient(app).post(
        "/api/chat",
        json={
            "customer_id": "",
            "session_id": "SESSION-API",
            "message": "Tiếp tục tư vấn",
            "stream": True,
        },
    )

    assert response.status_code == 200
    events = [line[6:] for line in response.text.splitlines() if line.startswith("data: {")]
    payloads = [json.loads(item) for item in events]
    assert payloads[0]["type"] == "call_brief"
    assert payloads[0]["call_brief"]["has_history"] is True
    assert payloads[1]["type"] == "response"
    assert payloads[1]["text"] == "Em tiếp tục hỗ trợ ạ."
    assert "profile_facts" not in response.text
    assert "0901234567" not in response.text
    assert 'data: {"done": true}\n\n' in response.text
