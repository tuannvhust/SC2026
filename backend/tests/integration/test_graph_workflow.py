from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import create_engine, text

from src.graph.graph import (
    build_graph,
    route_after_output_guardrail,
    route_after_plan,
)
from src.graph.builder import route_after_identity, route_after_persist_turn
from src.graph.nodes.input_nodes import (
    MAX_IDENTITY_ATTEMPTS,
    build_call_brief_node,
    input_guardrail_node,
    normalize_input_node,
    request_identity_node,
    resolve_identity_node,
)
from src.graph.nodes import input_nodes, persistence_nodes
from src.graph.nodes import planner as planner_node
from src.graph.nodes.safety_nodes import (
    _get_current_tool_results,
    handoff_to_human_node,
    output_guardrail_node,
    retry_node,
    route_after_retry,
)
from src.graph.state import AgentState
from src.memory.working.postgres_store import PostgresMemoryStore
from src.tools.tool_repository import crm_get_customer, memory_write


def _new_sqlite_memory_store(database_url):
    bootstrap = create_engine(database_url)
    with bootstrap.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    channel TEXT NOT NULL DEFAULT 'web_chat',
                    status TEXT NOT NULL DEFAULT 'active',
                    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_activity_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    ended_at TEXT,
                    finalized_at TEXT,
                    outcome TEXT,
                    handoff_reason TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    ended_at TEXT,
                    summary TEXT NOT NULL,
                    current_need TEXT,
                    outcome TEXT,
                    handoff_reason TEXT,
                    products_advised TEXT,
                    orders_summary TEXT,
                    open_questions TEXT,
                    open_blockers TEXT,
                    next_actions TEXT,
                    turn_count INTEGER,
                    started_at TEXT,
                    payload_json TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS working_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
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
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS profile_facts (
                    customer_id TEXT NOT NULL, profile_key TEXT NOT NULL,
                    profile_value TEXT, source_session_id TEXT, source_event_id TEXT,
                    source_kind TEXT DEFAULT 'customer_stated', confidence REAL,
                    updated_at TEXT, PRIMARY KEY(customer_id, profile_key)
                )
                """
            )
        )
    bootstrap.dispose()
    return PostgresMemoryStore(database_url)


def test_agent_state_uses_messages_without_separate_tool_fields():
    assert "messages" in AgentState.__annotations__
    assert "tool_results" not in AgentState.__annotations__
    assert "plan_action" not in AgentState.__annotations__


def test_input_guardrail_preserves_api_turn_id():
    result = input_guardrail_node(
        {
            "messages": [HumanMessage(content="Xin chào")],
            "session_id": "SESSION-API",
            "turn_id": "TURN-API",
        }
    )

    assert result["input_valid"] is True
    assert result["session_id"] == "SESSION-API"
    assert result["turn_id"] == "TURN-API"


def test_planner_routes_tool_calls_to_tool_node():
    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "handoff.transfer",
                "args": {},
                "id": "handoff-1",
                "type": "tool_call",
            }
        ],
    )

    assert route_after_plan({"messages": [message]}) == "tools"


def test_planner_routes_answer_and_clarification_to_output_guardrail():
    for content in ("Dạ, em có thể hỗ trợ.", "Anh/chị muốn chọn màu nào ạ?"):
        message = AIMessage(content=content)
        assert route_after_plan({"messages": [message]}) == "output_guardrail"
        assert output_guardrail_node({"messages": [message]}) == {
            "output_valid": True,
            "guardrail_feedback": None,
        }


def test_planner_retry_omits_rejected_trailing_ai_message(monkeypatch):
    user_message = HumanMessage(content="Giá sản phẩm là bao nhiêu?")
    rejected_answer = AIMessage(content="Giá là 1.000.000đ.")
    response = AIMessage(content="Em sẽ kiểm tra giá hiện tại ạ.")
    invoke = Mock(return_value=response)
    monkeypatch.setattr(planner_node, "planner_llm", Mock(invoke=invoke))

    result = planner_node.plan_step_node(
        {
            "messages": [user_message, rejected_answer],
            "guardrail_feedback": "The response price was not verified.",
        }
    )

    prompt_messages = invoke.call_args.args[0]
    # Compact prompt: current user message + retry feedback (no stale AI text).
    assert prompt_messages[2] is user_message
    assert "The response price was not verified." in prompt_messages[-1].content
    assert "The response price was not verified." in prompt_messages[1].content
    assert all(message is not rejected_answer for message in prompt_messages)
    assert result == {"messages": [response]}


def test_graph_sends_tool_results_back_to_planner():
    edges = {
        (edge.source, edge.target)
        for edge in build_graph().get_graph().edges
    }

    assert ("plan_step", "tools") in edges
    assert ("tools", "plan_step") in edges
    assert ("resolve_identity", "request_identity") in edges
    assert ("resolve_identity", "build_call_brief") in edges
    assert ("request_identity", "persist_turn") in edges
    assert ("plan_step", "output_guardrail") in edges
    assert ("output_guardrail", "retry_node") in edges
    assert ("retry_node", "plan_step") in edges
    assert ("retry_node", "handoff_to_human") in edges
    assert ("handoff_to_human", "persist_turn") in edges
    assert ("persist_turn", "persist_call") in edges
    assert ("persist_turn", "__end__") in edges
    assert ("persist_call", "__end__") in edges


def test_invalid_input_ends_without_undeclared_state_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(
        persistence_nodes,
        "_store",
        _new_sqlite_memory_store(
            f"sqlite+pysqlite:///{tmp_path / 'memory.sqlite3'}"
        ),
    )
    result = build_graph().invoke({"messages": [HumanMessage(content="x")], "session_id": "S000100"})

    assert result["input_valid"] is False
    assert "tool_results" not in result
    assert "plan_action" not in result


def test_input_nodes_only_update_declared_agent_state_fields(monkeypatch):
    class FakeProfileStore:
        def get_profile_facts(self, _customer_id):
            assert _customer_id
            return {}

        def get_profile_facts_with_provenance(self, _customer_id):
            assert _customer_id
            return {}

    class FakePostgresStore:
        def get_recent_episodes(self, _customer_id, limit=10):
            assert _customer_id
            return []

    monkeypatch.setattr(input_nodes, "get_profile_store", FakeProfileStore)
    monkeypatch.setattr(
        input_nodes,
        "get_postgres_memory_store",
        FakePostgresStore,
    )
    state = {"messages": [HumanMessage(content="sp 2tr")]}
    normalized = normalize_input_node(state)
    state.update(normalized)
    identity = resolve_identity_node(state)
    state.update(identity)
    brief = build_call_brief_node(state)

    assert normalized["customer_info"]["_input_text"] == "sản phẩm 2.000.000"
    assert set(normalized) | set(identity) | set(brief) <= AgentState.__annotations__.keys()


def test_unknown_identity_asks_for_name_and_phone_then_resolves_next_turn(monkeypatch):
    from langchain_core.messages import AIMessage

    class FakePostgresStore:
        def update_session_customer_id(self, _session_id, _customer_id):
            return None

    monkeypatch.setattr(
        input_nodes,
        "get_postgres_memory_store",
        FakePostgresStore,
    )

    def _fake_crm_invoke(payload):
        phone = payload.get("phone", "")
        if phone == "0901234567":
            return {
                "found": True,
                "customer_id": "CUST-1029",
                "name": None,
                "honorific": "Ch",
                "phone": "0901234567",
                "is_verified": True,
                "ambiguous": False,
                "error": None,
            }
        return {
            "found": False,
            "customer_id": None,
            "name": None,
            "honorific": None,
            "phone": phone,
            "is_verified": False,
            "ambiguous": False,
            "error": None,
        }

    monkeypatch.setattr(input_nodes, "crm_get_customer", type("FakeCrm", (), {"invoke": staticmethod(_fake_crm_invoke)})())

    state = {"messages": [HumanMessage(content="tư vấn giúp em")], "identity_attempts": 0}
    state.update(normalize_input_node(state))
    identity = resolve_identity_node(state)
    assert identity["customer_id"] is None
    assert identity["needs_identity"] is True
    state.update(identity)
    assert route_after_identity(state) == "request_identity"

    asked = request_identity_node(state)
    assert asked["identity_attempts"] == 1
    assert isinstance(asked["messages"][0], AIMessage)
    assert "số điện thoại" in asked["messages"][0].content
    # Combined ask must mention both name and phone in one question.
    assert "tên" in asked["messages"][0].content
    assert asked["missing_identity_fields"] == ["phone", "name"]
    assert asked["pending_need"]
    state.update(asked)

    # Customer replies with phone only: keep it, ask name without repeat.
    state["messages"].append(HumanMessage(content="sđt 0901234567"))
    state.update(normalize_input_node(state))
    partial = resolve_identity_node(state)
    assert partial["customer_info"]["phone"] == "0901234567"
    assert partial["needs_identity"] is True
    assert partial["missing_identity_fields"] == ["name"]
    state.update(partial)
    followup = request_identity_node(state)
    assert "không cần gửi lại số" in followup["messages"][0].content
    state.update(followup)

    # Customer replies with name + phone in the next turn.
    state["messages"].append(HumanMessage(content="mình tên Lan, sđt 0901234567"))
    state.update(normalize_input_node(state))
    resolved = resolve_identity_node(state)
    assert resolved["customer_id"] == "CUST-1029"
    assert resolved["customer_info"]["phone"] == "0901234567"
    assert resolved["customer_info"]["name"] == "Lan"
    assert resolved["needs_identity"] is False
    assert resolved["missing_identity_fields"] == []
    assert resolved["identity_attempts"] == 0
    # Original Turn-1 need survives identity turns.
    assert resolved["pending_need"]
    state.update(resolved)
    assert route_after_identity(state) == "build_call_brief"


def test_identity_falls_back_to_guest_after_max_attempts():
    assert route_after_identity({"needs_identity": True, "identity_attempts": 0}) == "request_identity"
    assert (
        route_after_identity(
            {"needs_identity": True, "identity_attempts": MAX_IDENTITY_ATTEMPTS}
        )
        == "build_call_brief"
    )
    assert route_after_identity({"needs_identity": False, "identity_attempts": 0}) == "build_call_brief"


def test_session_lifecycle_routes_ongoing_turn_to_end_and_ended_turn_to_commit():
    from langgraph.graph import END

    assert route_after_persist_turn({"session_ended": False}) == END
    assert route_after_persist_turn({"session_ended": True}) == "persist_call"


def test_persist_turn_stores_only_current_turn_and_tool_activity(tmp_path, monkeypatch):
    store = _new_sqlite_memory_store(
        f"sqlite+pysqlite:///{tmp_path / 'memory.sqlite3'}"
    )
    monkeypatch.setattr(persistence_nodes, "_store", store)
    messages = [
        HumanMessage(content="Previous turn."),
        AIMessage(content="Previous answer."),
        HumanMessage(content="Check this product."),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "catalog.search",
                    "args": {"query": "air purifier"},
                    "id": "catalog-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            name="catalog.search",
            content='{"items": [{"sku": "SKU-AP-X"}]}',
            tool_call_id="catalog-1",
        ),
        AIMessage(content="Found SKU-AP-X."),
    ]
    state = {
        "messages": messages,
        "session_id": "SESSION-1",
        "turn_id": "TURN-1",
        "customer_id": "CUST-1",
        "customer_info": {"phone": "0901234567", "_input_text": "private duplicate"},
        "input_valid": True,
    }

    first = persistence_nodes.persist_turn_node(state)
    second = persistence_nodes.persist_turn_node({**state, **first})
    events = store.get_session_events("SESSION-1")

    assert first["turn_number"] == second["turn_number"] == 1
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["identity"] == {"phone": "0901234567", "customer_id": "CUST-1"}
    assert payload["tool_calls"][0]["name"] == "catalog.search"
    assert payload["tool_results"][0]["result"]["items"][0]["sku"] == "SKU-AP-X"
    assert all("Previous" not in str(message) for message in payload["messages"])

    next_turn = persistence_nodes.persist_turn_node(
        {
            **state,
            "turn_id": "TURN-2",
            "messages": [
                HumanMessage(content="How much is it?"),
                AIMessage(content="The current quote is 4.401.000 VND."),
            ],
        }
    )
    events = store.get_session_events("SESSION-1")
    assert next_turn["turn_number"] == 2
    assert [event["turn_number"] for event in events] == [1, 2]


def test_persist_call_writes_episode_and_only_explicit_profile_facts(
    tmp_path,
    monkeypatch,
):
    store = _new_sqlite_memory_store(
        f"sqlite+pysqlite:///{tmp_path / 'memory.sqlite3'}"
    )
    monkeypatch.setattr(persistence_nodes, "_store", store)

    class FakeProfileStore:
        updates = []

        def add_profile_facts(self, customer_id, facts, session_id):
            self.updates.append((customer_id, facts, session_id))

    profile_store = FakeProfileStore()
    monkeypatch.setattr(persistence_nodes, "get_profile_store", lambda: profile_store)
    messages = [
        HumanMessage(content="Tôi muốn tư vấn máy lọc khí."),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "catalog.search",
                    "args": {"query": "máy lọc khí"},
                    "id": "catalog-1",
                    "type": "tool_call",
                },
                {
                    "name": "pricing.get_quote",
                    "args": {"sku": "SKU-AP-X"},
                    "id": "quote-1",
                    "type": "tool_call",
                },
                {
                    "name": "memory.write",
                    "args": {"key": "preferred_category", "value": "air purifier"},
                    "id": "memory-1",
                    "type": "tool_call",
                },
            ],
        ),
        ToolMessage(
            name="catalog.search",
            content='{"items": [{"sku": "SKU-AP-X", "name": "AirPure X"}]}',
            tool_call_id="catalog-1",
        ),
        ToolMessage(
            name="pricing.get_quote",
            content='{"final_price_vnd": 4401000, "applied_promos": ["PROMO-10PCT"]}',
            tool_call_id="quote-1",
        ),
        ToolMessage(
            name="memory.write",
            content='{"status": "queued_for_session_commit", "key": "preferred_category"}',
            tool_call_id="memory-1",
        ),
        AIMessage(content="Dạ, mẫu AirPure X giá 4.401.000đ ạ."),
    ]
    state = {
        "messages": messages,
        "session_id": "SESSION-2",
        "turn_id": "TURN-1",
        "customer_id": "CUST-2",
        "session_ended": True,
        "customer_info": {"phone": "0901234567", "channel": "web_chat"},
        "call_brief": {
            "open_blockers": ["cân nhắc giá"],
            "open_questions": [],
        },
    }

    persistence_nodes.persist_turn_node(state)
    persistence_nodes.persist_call_node(state)
    episode = store.get_episode("SESSION-2")

    assert episode["outcome"] == "khac"
    assert episode["products_advised"] == [
        {
            "sku": "SKU-AP-X",
            "name": "AirPure X",
            "price_quoted_vnd": 4_401_000,
            "applied_promos": ["PROMO-10PCT"],
        }
    ]
    assert episode["open_blockers"] == ["cân nhắc giá"]
    assert episode["profile_facts_written"] == ["preferred_category"]
    assert profile_store.updates == [
        (
            "CUST-2",
            [{
                "key": "preferred_category",
                "value": "air purifier",
                "source_event_id": store.get_session_events("SESSION-2")[0]["event_id"],
                "source_kind": "customer_stated",
            }],
            "SESSION-2",
        )
    ]


def test_ongoing_turn_does_not_write_episode_or_profile(tmp_path, monkeypatch):
    store = _new_sqlite_memory_store(
        f"sqlite+pysqlite:///{tmp_path / 'memory.sqlite3'}"
    )
    monkeypatch.setattr(persistence_nodes, "_store", store)

    class FakeProfileStore:
        def add_profile_facts(self, customer_id, facts, session_id):
            raise AssertionError(
                f"Unexpected profile write for {customer_id}: {facts} ({session_id})."
            )

    monkeypatch.setattr(persistence_nodes, "get_profile_store", FakeProfileStore)
    state = {
        "messages": [HumanMessage(content="Tôi thích máy lọc khí.")],
        "session_id": "SESSION-ONGOING",
        "turn_id": "TURN-1",
        "customer_id": "CUST-3",
        "session_ended": False,
    }

    persistence_nodes.persist_turn_node(state)
    assert persistence_nodes.persist_call_node(state) == {}
    assert store.get_episode("SESSION-ONGOING") is None


def test_persist_call_skips_empty_session_and_is_idempotent(tmp_path, monkeypatch):
    store = _new_sqlite_memory_store(
        f"sqlite+pysqlite:///{tmp_path / 'p2.sqlite3'}"
    )
    monkeypatch.setattr(persistence_nodes, "_store", store)
    state = {
        "session_id": "SESSION-EMPTY",
        "customer_id": "CUST-EMPTY",
        "session_ended": True,
    }
    first = persistence_nodes.persist_call_node(state)
    assert first["finalized"] is True
    assert first["empty_session"] is True
    assert store.get_episode("SESSION-EMPTY") is None


def test_profile_fact_is_written_to_postgres_only():
    from types import SimpleNamespace

    from src.memory.profile.profile_store import ProfileStore

    class FakePostgresStore:
        def save_profile_facts(self, **kwargs):
            self.saved = kwargs

    class FakeVectorStore:
        def init_collection(self, collection_name, dense_dim):
            self.initialized = (collection_name, dense_dim)

        class Client:
            def upsert(self, **kwargs):
                self.upserted = kwargs

        client = Client()

    vector_store = FakeVectorStore()
    postgres_store = FakePostgresStore()
    connections = SimpleNamespace(
        vector_store=vector_store,
        dense_embedder=SimpleNamespace(embed_text=lambda _text: [0.1, 0.2]),
    )
    ProfileStore(postgres_store, connections).add_profile_facts(
        "CUST-4",
        [{"key": "preferred_category", "value": "air purifier"}],
        "SESSION-4",
    )

    assert not hasattr(vector_store, "initialized")
    assert postgres_store.saved["customer_id"] == "CUST-4"
    assert postgres_store.saved["session_id"] == "SESSION-4"
    assert postgres_store.saved["facts"] == [
        {"key": "preferred_category", "value": "air purifier"}
    ]


def test_profile_commit_survives_qdrant_failure_and_versions_history(tmp_path):
    from types import SimpleNamespace

    from src.memory.profile.profile_store import ProfileStore

    postgres = _new_sqlite_memory_store(
        f"sqlite+pysqlite:///{tmp_path / 'profile.sqlite3'}"
    )
    with postgres.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO conversation_sessions (session_id, customer_id) VALUES ('SESSION-A', 'CUST-P2'), ('SESSION-B', 'CUST-P2')")
        )

    class FailingVectorStore:
        def init_collection(self, *args, **kwargs):
            raise RuntimeError("qdrant down")

    connections = SimpleNamespace(
        vector_store=FailingVectorStore(),
        dense_embedder=SimpleNamespace(embed_text=lambda _text: [0.1]),
    )
    ProfileStore(postgres, connections).add_profile_facts(
        "CUST-P2", [{"key": "size", "value": "M"}], "SESSION-A"
    )
    ProfileStore(postgres, connections).add_profile_facts(
        "CUST-P2", [{"key": "size", "value": "L"}], "SESSION-B"
    )
    assert postgres.get_profile_facts("CUST-P2") == {"size": "L"}
    try:
        postgres.get_profile_fact_history("CUST-P2", "size")
        raise AssertionError("Simplified schema must not expose profile history")
    except RuntimeError as error:
        assert "simplified schema" in str(error)


def test_memory_write_queues_profile_fact_until_session_commit():
    result = memory_write.invoke(
        {
            "key": "preferred_category",
            "value": "air purifier",
            "provenance_session_id": "SESSION-5",
        }
    )

    assert result["status"] == "queued_for_session_commit"
    assert result["provenance_session_id"] == "SESSION-5"


def test_output_guardrail_rejects_prices_that_disagree_with_quote():
    messages = [
        HumanMessage(content="Giá mẫu này bao nhiêu?"),
        AIMessage(
            content="Dạ, giá hiện tại là 4.890.000đ ạ.",
        ),
        ToolMessage(
            name="pricing.get_quote",
            content='{"final_price_vnd": 4401000, "applied_promos": ["PROMO-10PCT"]}',
            tool_call_id="quote-1",
        ),
        AIMessage(content="Dạ giá hiện tại là 4.890.000đ ạ."),
    ]

    result = output_guardrail_node({"messages": messages})

    assert result["output_valid"] is False
    assert "pricing.get_quote" in result["guardrail_feedback"]


def test_guardrail_checks_tool_results_only_from_current_customer_turn():
    previous_turn_tool = ToolMessage(
        name="pricing.get_quote",
        content='{"final_price_vnd": 1000000}',
        tool_call_id="quote-old",
    )
    customer_message = HumanMessage(content="Giá hiện tại là bao nhiêu?")
    current_quote = ToolMessage(
        name="pricing.get_quote",
        content='{"final_price_vnd": 4401000}',
        tool_call_id="quote-current",
    )
    response = AIMessage(content="Dạ giá là 4.401.000đ ạ.")
    messages = [previous_turn_tool, customer_message, current_quote, response]

    assert _get_current_tool_results(messages) == [current_quote]
    assert output_guardrail_node({"messages": messages})["output_valid"] is True


def test_output_guardrail_ignores_user_budget_constraint():
    messages = [
        HumanMessage(content="Tìm máy lọc không khí dưới 10 triệu"),
        ToolMessage(
            name="pricing.get_quote",
            content='{"sku": "SKU-XM-4L", "final_price_vnd": 2990000}',
            tool_call_id="quote-1",
        ),
        AIMessage(
            content="Dạ bên em có máy lọc dưới 10 triệu phù hợp với anh/chị: Xiaomi Smart 4 Lite giá 2.990.000đ ạ."
        ),
    ]

    result = output_guardrail_node({"messages": messages})
    assert result["output_valid"] is True


def test_output_guardrail_allows_discount_amount():
    messages = [
        HumanMessage(content="Máy này có giảm giá không?"),
        ToolMessage(
            name="pricing.get_quote",
            content='{"sku": "SKU-AP-PRO", "list_price_vnd": 7990000, "final_price_vnd": 7690000, "discount_vnd": 300000}',
            tool_call_id="quote-1",
        ),
        AIMessage(
            content="Dạ máy AirPure Pro giá gốc 7.990.000đ, đang giảm 300.000đ còn 7.690.000đ ạ."
        ),
    ]

    result = output_guardrail_node({"messages": messages})
    assert result["output_valid"] is True




def test_output_guardrail_checks_inventory_and_promotions():
    messages = [
        HumanMessage(content="Mẫu này còn hàng và có khuyến mãi không?"),
        ToolMessage(
            name="inventory.check",
            content='{"in_stock": false}',
            tool_call_id="inventory-1",
        ),
        ToolMessage(
            name="pricing.get_quote",
            content='{"applied_promos": [], "expired_promos": ["PROMO-OLD"], "freeship": false}',
            tool_call_id="quote-1",
        ),
        AIMessage(
            content="Sản phẩm còn hàng, áp dụng PROMO-OLD và được miễn phí vận chuyển."
        ),
    ]

    result = output_guardrail_node({"messages": messages})

    assert result["output_valid"] is False
    assert "inventory.check" in result["guardrail_feedback"]
    assert "PROMO-OLD" in result["guardrail_feedback"]


def test_output_guardrail_rejects_hallucinated_gifts():
    messages = [
        HumanMessage(content="Máy lọc không khí này có ưu đãi gì không?"),
        ToolMessage(
            name="pricing.get_quote",
            content='{"sku": "SKU-AP-Y", "final_price_vnd": 3500000, "applied_promos": [], "gifts": []}',
            tool_call_id="quote-1",
        ),
        AIMessage(content="Dạ máy có giá 3.500.000đ và được tặng kèm 1 bộ lọc ạ."),
    ]

    result = output_guardrail_node({"messages": messages})
    assert result["output_valid"] is False
    assert "Dữ liệu quà tặng" in result["guardrail_feedback"]
    assert "SKU-AP-Y" in result["guardrail_feedback"]


def test_output_guardrail_allows_explicit_gift_denial():
    messages = [
        HumanMessage(content="Mẫu AirPure Pro có quà gì không?"),
        ToolMessage(
            name="pricing.get_quote",
            content='{"sku": "SKU-AP-PRO", "final_price_vnd": 7690000, "gifts": []}',
            tool_call_id="quote-1",
        ),
        AIMessage(
            content="Dạ AirPure Pro giá 7.690.000đ. Quà tặng kèm: Mẫu này hiện không có quà tặng kèm ạ."
        ),
    ]

    result = output_guardrail_node({"messages": messages})
    assert result["output_valid"] is True


def test_output_guardrail_blocks_cross_sku_gift_borrowing():
    messages = [
        HumanMessage(content="Hai mẫu này quà thế nào?"),
        ToolMessage(
            name="pricing.get_quote",
            content='{"sku": "SKU-A", "gifts": [{"promo_code": "G1", "sku": "GIFT-1"}]}',
            tool_call_id="quote-a",
        ),
        ToolMessage(
            name="pricing.get_quote",
            content='{"sku": "SKU-B", "gifts": []}',
            tool_call_id="quote-b",
        ),
        AIMessage(content="Dạ SKU-B được tặng kèm 1 bộ lọc ạ."),
    ]

    result = output_guardrail_node({"messages": messages})
    assert result["output_valid"] is False
    assert "SKU-B" in result["guardrail_feedback"]


def test_output_guardrail_cleans_signature_artifacts():
    messages = [
        HumanMessage(content="Giá bao nhiêu?"),
        ToolMessage(
            name="pricing.get_quote",
            content='{"final_price_vnd": 1000000}',
            tool_call_id="quote-1",
        ),
        AIMessage(
            content="Dạ giá là 1.000.000đ ạ.\n```signature\nsig_abc123_encrypted_long_hash\n```\n[signature: meta]"
        ),
    ]

    result = output_guardrail_node({"messages": messages})
    assert result["output_valid"] is True



def test_retry_routes_to_planner_twice_then_handoff():
    assert route_after_output_guardrail({"output_valid": False}) == "retry_node"
    assert retry_node({"retry_count": 0})["retry_count"] == 1
    assert route_after_retry({"retry_count": 1}) == "plan_step"
    assert route_after_retry({"retry_count": 2}) == "plan_step"
    assert route_after_retry({"retry_count": 3}) == "handoff_to_human"


def test_handoff_requires_valid_customer_phone():
    result = handoff_to_human_node(
        {
            "customer_info": {},
            "guardrail_feedback": "Repeated output validation failure.",
        }
    )

    assert result["is_handoff"] is False
    assert result["output_valid"] is False
    assert "valid customer phone" in result["guardrail_feedback"]


def test_handoff_submits_schema_valid_brief(monkeypatch):
    from src.graph.nodes import safety_nodes

    submitted = {}

    class FakeHandoffTool:
        def invoke(self, payload):
            submitted.update(payload)
            return {"status": "queued"}

    monkeypatch.setattr(safety_nodes, "handoff_transfer", FakeHandoffTool())
    result = handoff_to_human_node(
        {
            "customer_id": "CUST-1029",
            "customer_info": {
                "phone": "0901234567",
                "name": "Hoa",
                "sessions": [{"session_id": "SESSION-1"}],
            },
            "call_brief": {
                "is_returning": True,
                "products_advised": [
                    {
                        "sku": "SKU-AP-X",
                        "price_quoted_vnd": 4_401_000,
                        "promo_code": "PROMO-10PCT",
                    }
                ],
                "open_blockers": ["chờ hỏi chồng"],
                "open_questions": [],
                "profile_facts": {},
            },
            "retry_count": 3,
            "guardrail_feedback": "Repeated guardrail validation failures.",
        }
    )

    brief = submitted["brief"]
    assert result["is_handoff"] is True
    assert result["handoff_reason"] == "loi_he_thong"
    assert brief["customer_phone"] == "0901234567"
    assert brief["product_advised"] == "SKU-AP-X"
    assert brief["price_quoted_vnd"] == 4_401_000
    assert brief["history_refs"] == ["SESSION-1"]


def test_planner_calls_catalog_search_on_shopping_inquiry(monkeypatch):
    user_message = HumanMessage(content="Tư vấn giúp anh máy lọc không khí dưới 5 triệu")
    expected_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "catalog.search",
                "args": {"query": "máy lọc không khí", "max_price_vnd": 5_000_000},
                "id": "call-catalog-1",
                "type": "tool_call",
            }
        ],
    )
    invoke = Mock(return_value=expected_response)
    monkeypatch.setattr(planner_node, "planner_llm", Mock(invoke=invoke))

    result = planner_node.plan_step_node(
        {
            "messages": [user_message],
            "call_brief": {},
        }
    )

    prompt_messages = invoke.call_args.args[0]
    assert prompt_messages[-1] is user_message
    assert result == {"messages": [expected_response]}
    assert route_after_plan(result) == "tools"
    assert result["messages"][0].tool_calls[0]["name"] == "catalog.search"

