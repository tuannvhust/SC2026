"""Regression tests for identity collection, CallBrief and planner prompt."""

from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.graph.builder import route_after_identity
from src.graph.nodes import input_nodes, persistence_nodes
from src.graph.nodes import planner as planner_node
from src.graph.nodes.input_nodes import (
    build_call_brief_node,
    normalize_input_node,
    request_identity_node,
    resolve_identity_node,
)
from src.tools.tool_repository import crm_get_customer


class _FakePostgresStore:
    def update_session_customer_id(self, _session_id, _customer_id):
        return None

    def get_session_events(self, _session_id, customer_id=None, limit=20):
        return []

    def get_recent_episodes(self, _customer_id, limit=10):
        return []

    def save_call_brief(self, _session_id, _customer_id, _call_brief):
        return 1


class _FakeProfileStore:
    def __init__(self, facts=None):
        self._facts = facts or {}

    def get_profile_facts(self, _customer_id):
        return dict(self._facts)

    def get_profile_facts_with_provenance(self, _customer_id):
        return {
            key: {
                "value": value,
                "source_session_id": None,
                "updated_at": None,
            }
            for key, value in self._facts.items()
        }


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


def _patch_stores(monkeypatch, profile_facts=None):
    monkeypatch.setattr(input_nodes, "get_postgres_memory_store", _FakePostgresStore)
    monkeypatch.setattr(
        input_nodes, "get_profile_store", lambda: _FakeProfileStore(profile_facts)
    )
    monkeypatch.setattr(
        input_nodes,
        "crm_get_customer",
        type("FakeCrm", (), {"invoke": staticmethod(_fake_crm_invoke)})(),
    )


def test_1_customer_gives_name_and_phone_upfront(monkeypatch):
    _patch_stores(monkeypatch)
    state = {"messages": [HumanMessage(content="mình tên Lan, sđt 0901234567")]}
    state.update(normalize_input_node(state))
    resolved = resolve_identity_node(state)
    assert resolved["needs_identity"] is False
    assert route_after_identity({**state, **resolved}) == "build_call_brief"


def test_2_phone_first_then_name(monkeypatch):
    _patch_stores(monkeypatch)
    state = {"messages": [HumanMessage(content="sđt 0901234567")]}
    state.update(normalize_input_node(state))
    partial = resolve_identity_node(state)
    assert partial["needs_identity"] is True
    assert partial["missing_identity_fields"] == ["name"]
    state.update(partial)
    assert "không cần gửi lại số" in request_identity_node(state)["messages"][0].content


def test_3_existing_crm_profile_name_is_trusted(monkeypatch):
    _patch_stores(monkeypatch, profile_facts={"name": "Hoa"})
    state = {
        "messages": [HumanMessage(content="mình tên Lan, sđt 0901234567")],
        "customer_id": "CUST-1029",
        "customer_info": {"phone": "0901234567", "name": "Hoa"},
    }
    state.update(normalize_input_node(state))
    brief = build_call_brief_node({**state, **resolve_identity_node(state)})
    assert brief["call_brief"]["customer_name"] == "Hoa"
    assert brief["call_brief"]["customer_id"] == "CUST-1029"


def test_4_turn1_need_survives_identity_turn(monkeypatch):
    _patch_stores(monkeypatch)
    state = {"messages": [HumanMessage(content="cần máy lọc không khí phòng 20m2")]}
    state.update(normalize_input_node(state))
    first = resolve_identity_node(state)
    assert first["pending_need"]
    state.update(first)
    state.update(request_identity_node(state))
    state["messages"].append(HumanMessage(content="mình tên Lan, sđt 0901234567"))
    state.update(normalize_input_node(state))
    resolved = resolve_identity_node(state)
    brief = build_call_brief_node({**state, **resolved})
    assert "máy lọc" in (brief["call_brief"]["current_need"] or "")


def test_5_call_brief_has_expected_fields(monkeypatch):
    _patch_stores(monkeypatch)
    state = {
        "messages": [HumanMessage(content="mình tên Lan, sđt 0901234567")],
        "customer_id": "CUST-1029",
        "customer_info": {"phone": "0901234567", "name": "Lan"},
        "pending_need": "cần máy lọc không khí",
    }
    brief = build_call_brief_node(state)["call_brief"]
    for field in (
        "customer_id",
        "customer_name",
        "current_need",
        "constraints",
        "profile_facts",
        "tool_summary",
        "suggested_opening",
    ):
        assert field in brief
    assert brief["customer_name"] == "Lan"
    assert brief != state["messages"]


def test_6_planner_skips_stale_tool_json(monkeypatch):
    stale = ToolMessage(
        content='{"sku": "OLD", "final_price_vnd": 1}',
        name="pricing.get_quote",
        tool_call_id="old-1",
    )
    stale_call = AIMessage(
        content="",
        tool_calls=[
            {"name": "pricing.get_quote", "args": {}, "id": "old-1", "type": "tool_call"}
        ],
    )
    current_call = AIMessage(
        content="",
        tool_calls=[
            {"name": "catalog.search", "args": {}, "id": "new-1", "type": "tool_call"}
        ],
    )
    current_result = ToolMessage(
        content='{"items": [{"sku": "SKU-AP-X"}]}',
        name="catalog.search",
        tool_call_id="new-1",
    )
    state = {
        "messages": [
            HumanMessage(content="turn cũ"),
            stale_call,
            stale,
            HumanMessage(content="AirPure Y giá sao?"),
            current_call,
            current_result,
        ],
        "call_brief": {"customer_name": "Lan"},
    }
    prompt = planner_node.build_planner_prompt(state)
    prompt_text = " ".join(
        message.content if isinstance(message.content, str) else str(message.content)
        for message in prompt
    )
    assert '"OLD"' not in prompt_text
    assert "SKU-AP-X" in prompt_text
    assert sum(isinstance(message, ToolMessage) for message in prompt) == 1

    captured = {}

    def _fake_invoke(messages):
        captured["prompt"] = messages
        return AIMessage(content="ok")

    monkeypatch.setattr(planner_node, "planner_llm", Mock(invoke=_fake_invoke))
    planner_node.plan_step_node(state)
    assert captured["prompt"] is not state["messages"]


def test_6b_multi_tool_chain_kept_intact_without_old_json(monkeypatch):
    """catalog -> quote x3 -> inventory in one turn: all pairs survive trim."""
    from src.graph.nodes import planner as planner_node

    old_tool_call = AIMessage(
        content="",
        tool_calls=[
            {"name": "pricing.get_quote", "args": {}, "id": "old-q", "type": "tool_call"}
        ],
    )
    old_result = ToolMessage(
        content='{"sku": "SKU-OLD", "final_price_vnd": 1}',
        name="pricing.get_quote",
        tool_call_id="old-q",
    )
    chain_call = AIMessage(
        content="",
        tool_calls=[
            {"name": "catalog.search", "args": {}, "id": "c1", "type": "tool_call"},
            {"name": "pricing.get_quote", "args": {"sku": "SKU-AP-X"}, "id": "q1", "type": "tool_call"},
            {"name": "pricing.get_quote", "args": {"sku": "SKU-AP-Y"}, "id": "q2", "type": "tool_call"},
            {"name": "pricing.get_quote", "args": {"sku": "SKU-AP-PRO"}, "id": "q3", "type": "tool_call"},
            {"name": "inventory.check", "args": {"sku": "SKU-AP-Y"}, "id": "i1", "type": "tool_call"},
        ],
    )
    results = [
        ToolMessage(content='{"items": []}', name="catalog.search", tool_call_id="c1"),
        ToolMessage(
            content='{"sku": "SKU-AP-X", "final_price_vnd": 4890000}',
            name="pricing.get_quote",
            tool_call_id="q1",
        ),
        ToolMessage(
            content='{"sku": "SKU-AP-Y", "final_price_vnd": 5200000}',
            name="pricing.get_quote",
            tool_call_id="q2",
        ),
        ToolMessage(
            content='{"sku": "SKU-AP-PRO", "final_price_vnd": 7990000}',
            name="pricing.get_quote",
            tool_call_id="q3",
        ),
        ToolMessage(
            content='{"sku": "SKU-AP-Y", "in_stock": true, "stock": 15}',
            name="inventory.check",
            tool_call_id="i1",
        ),
    ]
    state = {
        "messages": [
            HumanMessage(content="turn cũ"),
            old_tool_call,
            old_result,
            HumanMessage(content="so sánh 3 mẫu máy lọc"),
            chain_call,
            *results,
        ],
        "call_brief": {"customer_name": "An"},
    }
    prompt = planner_node.build_planner_prompt(state)
    text = " ".join(
        m.content if isinstance(m.content, str) else str(m.content) for m in prompt
    )
    # All current-turn results present, old JSON absent.
    assert "SKU-AP-X" in text and "SKU-AP-Y" in text and "SKU-AP-PRO" in text
    assert '"SKU-OLD"' not in text
    assert sum(isinstance(m, ToolMessage) for m in prompt) == 5

    def _fake_invoke(messages):
        captured["prompt"] = messages
        return AIMessage(content="ok")

    captured = {}
    monkeypatch.setattr(planner_node, "planner_llm", Mock(invoke=_fake_invoke))
    planner_node.plan_step_node(state)
    est = planner_node._estimate_tokens(
        "".join(planner_node._message_text_safe(m) for m in captured["prompt"])
    )
    # Budget sanity: compact prompt must stay far below the 7000 ITPM limit.
    assert est < 7000
    assert planner_node._prompt_size_chars(captured["prompt"]) < planner_node.MAX_PLANNER_PROMPT_CHARS


def test_7_valid_price_inventory_pass_guardrail():
    from src.graph.nodes.safety_nodes import output_guardrail_node

    quote = ToolMessage(
        content=(
            '{"sku": "SKU-AP-X", "final_price_vnd": 4401000, '
            '"applied_promos": ["PROMO-10PCT"], "gifts": [], '
            '"ineligible_promos": [], "expired_promos": []}'
        ),
        name="pricing.get_quote",
        tool_call_id="quote-1",
    )
    stock = ToolMessage(
        content='{"sku": "SKU-AP-X", "in_stock": true}',
        name="inventory.check",
        tool_call_id="stock-1",
    )
    calls = AIMessage(
        content="",
        tool_calls=[
            {"name": "pricing.get_quote", "args": {}, "id": "quote-1", "type": "tool_call"},
            {"name": "inventory.check", "args": {}, "id": "stock-1", "type": "tool_call"},
        ],
    )
    state = {
        "messages": [
            HumanMessage(content="Giá bao nhiêu?"),
            calls,
            quote,
            stock,
            AIMessage(content="Dạ giá hiện tại là 4.401.000đ, còn hàng ạ."),
        ]
    }
    assert output_guardrail_node(state)["output_valid"] is True


def test_8_prompt_budget_and_quota_handling(monkeypatch):
    state = {
        "messages": [HumanMessage(content="x" * 50000)],
        "call_brief": {"current_session_history": ["hi"] * 50},
    }
    prompt = planner_node.build_planner_prompt(state)
    assert len(prompt) <= 5

    class QuotaError(RuntimeError):
        pass

    def _raise(_messages):
        raise QuotaError("413 Limit 7000, Requested 7232 ITPM")

    monkeypatch.setattr(planner_node, "planner_llm", Mock(invoke=_raise))
    result = planner_node.plan_step_node({"messages": [HumanMessage(content="hi")]})
    assert result["messages"][0].content
    assert "quota" in (result.get("guardrail_feedback") or "").lower()


def test_identity_snapshot_persists_missing_fields_and_need():
    state = {
        "customer_info": {"phone": "0901234567", "channel": "web_chat"},
        "customer_id": None,
        "needs_identity": True,
        "identity_attempts": 1,
        "missing_identity_fields": ["name"],
        "pending_need": "cần máy lọc",
    }
    snapshot = persistence_nodes._identity_snapshot(state)
    assert snapshot["missing_identity_fields"] == ["name"]
    assert snapshot["pending_need"] == "cần máy lọc"
