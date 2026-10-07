from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.graph.graph import (
    build_graph,
    route_after_output_guardrail,
    route_after_plan,
)
from src.graph.builder import route_after_persist_turn
from src.graph.nodes.input_nodes import (
    build_call_brief_node,
    normalize_input_node,
    resolve_identity_node,
)
from src.graph.nodes import input_nodes, persistence_nodes
from src.graph.nodes.safety_nodes import (
    _get_current_tool_results,
    handoff_to_human_node,
    output_guardrail_node,
    retry_node,
    route_after_retry,
)
from src.graph.state import AgentState
from src.memory.working.sqlite_store import SQLiteMemoryStore
from src.tools.tool_repository import memory_write


def test_agent_state_uses_messages_without_separate_tool_fields():
    assert "messages" in AgentState.__annotations__
    assert "tool_results" not in AgentState.__annotations__
    assert "plan_action" not in AgentState.__annotations__


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


def test_graph_sends_tool_results_back_to_planner():
    edges = {
        (edge.source, edge.target)
        for edge in build_graph().get_graph().edges
    }

    assert ("plan_step", "tools") in edges
    assert ("tools", "plan_step") in edges
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
        SQLiteMemoryStore(tmp_path / "memory.sqlite3"),
    )
    result = build_graph().invoke({"messages": [HumanMessage(content="x")]})

    assert result["input_valid"] is False
    assert "tool_results" not in result
    assert "plan_action" not in result


def test_input_nodes_only_update_declared_agent_state_fields(monkeypatch):
    class FakeProfileStore:
        def get_profile_facts(self, _customer_id):
            assert _customer_id
            return {}

    class FakeSQLiteStore:
        def get_recent_episodes(self, _customer_id):
            assert _customer_id
            return []

    monkeypatch.setattr(input_nodes, "get_profile_store", FakeProfileStore)
    monkeypatch.setattr(input_nodes, "SQLiteMemoryStore", FakeSQLiteStore)
    state = {"messages": [HumanMessage(content="sp 2tr")]}
    normalized = normalize_input_node(state)
    state.update(normalized)
    identity = resolve_identity_node(state)
    state.update(identity)
    brief = build_call_brief_node(state)

    assert normalized["customer_info"]["_input_text"] == "sản phẩm 2.000.000"
    assert set(normalized) | set(identity) | set(brief) <= AgentState.__annotations__.keys()


def test_session_lifecycle_routes_ongoing_turn_to_end_and_ended_turn_to_commit():
    from langgraph.graph import END

    assert route_after_persist_turn({"session_ended": False}) == END
    assert route_after_persist_turn({"session_ended": True}) == "persist_call"


def test_persist_turn_stores_only_current_turn_and_tool_activity(tmp_path, monkeypatch):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
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
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
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

    assert episode["outcome"] == "completed"
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
            [{"key": "preferred_category", "value": "air purifier"}],
            "SESSION-2",
        )
    ]


def test_ongoing_turn_does_not_write_episode_or_profile(tmp_path, monkeypatch):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
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


def test_mem0_profile_fact_records_session_provenance(monkeypatch):
    from src.memory.profile import mem0_store

    class FakeMemory:
        calls = []

        def add(self, content, **kwargs):
            self.calls.append((content, kwargs))

    memory = FakeMemory()
    monkeypatch.setattr(mem0_store, "_get_memory", lambda: memory)

    mem0_store.Mem0ProfileStore().add_profile_facts(
        "CUST-4",
        [{"key": "preferred_category", "value": "air purifier"}],
        "SESSION-4",
    )

    assert memory.calls[0][1]["metadata"]["provenance_session_id"] == "SESSION-4"


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
