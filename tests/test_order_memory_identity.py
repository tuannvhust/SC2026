"""Regression: order delivery date, memory provenance commit, identity reuse."""

from datetime import date, datetime, timedelta

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.graph.nodes import input_nodes, persistence_nodes
from src.graph.nodes.input_nodes import normalize_input_node, resolve_identity_node
from src.tools.tool_repository import compute_estimated_delivery, memory_write, order_create


def test_order_delivery_never_in_past_and_skips_sunday_and_holiday():
    # Friday order -> Saturday delivery (>= order date, not Sunday).
    friday = "2026-10-16"
    delivery = compute_estimated_delivery(friday)
    assert delivery >= friday
    assert datetime.strptime(delivery, "%Y-%m-%d").weekday() != 6

    # Saturday order -> next Monday (Sunday skipped).
    saturday = "2026-10-17"
    assert compute_estimated_delivery(saturday) == "2026-10-19"

    # Order before 30/04 + 01/05 holidays -> next working day after 01/05.
    holiday_run = compute_estimated_delivery("2026-04-29")
    assert holiday_run >= "2026-05-02"
    assert holiday_run not in {"2026-04-30", "2026-05-01"}

    # No fixed date: default (today) must produce a future-or-today-lead date.
    today_default = compute_estimated_delivery(None)
    assert today_default >= date.today().isoformat()
    assert today_default != "2026-10-10"

    # Tool output wired to the same helper.
    result = order_create.invoke(
        {
            "customer_phone": "0912345678",
            "sku": "SKU-AP-Y",
            "qty": 1,
            "price_vnd": 5200000,
            "payment": "COD",
            "on": "2026-10-16",
        }
    )
    assert result["estimated_delivery"] == compute_estimated_delivery("2026-10-16")


def test_memory_write_provenance_then_commit_and_read_back(tmp_path, monkeypatch):
    store = persistence_nodes.PostgresMemoryStore(
        f"sqlite+pysqlite:///{tmp_path / 'memory.sqlite3'}"
    )
    monkeypatch.setattr(persistence_nodes, "_store", store)

    # 1) Tool call includes provenance_session_id from the CallBrief session.
    tool_result = memory_write.invoke(
        {
            "key": "customer_name",
            "value": "An",
            "provenance_session_id": "SESSION-1",
        }
    )
    assert tool_result["status"] == "queued_for_session_commit"
    assert tool_result["provenance_session_id"] == "SESSION-1"

    # 2) persist_turn records the memory.write call/result pair.
    messages = [
        HumanMessage(content="Tên mình là An nhé"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "memory.write",
                    "args": {
                        "key": "customer_name",
                        "value": "An",
                        "provenance_session_id": "SESSION-1",
                    },
                    "id": "mem-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            name="memory.write",
            content=str(tool_result),
            tool_call_id="mem-1",
        ),
    ]
    state = {
        "messages": messages,
        "session_id": "SESSION-1",
        "turn_id": "TURN-1",
        "customer_id": "CUST-1029",
        "customer_info": {"phone": "0912345678", "name": "An"},
        "input_valid": True,
        "session_ended": True,
    }
    persistence_nodes.persist_turn_node(state)

    # 3) persist_call commits queued facts with session provenance.
    committed = {}

    class ReadableProfileStore:
        def add_profile_facts(self, customer_id, facts, session_id):
            committed["customer_id"] = customer_id
            committed["session_id"] = session_id
            committed["facts"] = facts

        def get_profile_facts(self, customer_id):
            return {
                fact["key"]: fact["value"]
                for fact in committed.get("facts", [])
                if committed.get("customer_id") == customer_id
            }

    monkeypatch.setattr(
        persistence_nodes, "get_profile_store", lambda: ReadableProfileStore()
    )
    persistence_nodes.persist_call_node(state)

    # 4) Read back in a later turn/session — not just the queue message.
    assert committed["session_id"] == "SESSION-1"
    assert committed["customer_id"] == "CUST-1029"
    read_back = ReadableProfileStore().get_profile_facts("CUST-1029")
    assert read_back == {"customer_name": "An"}


def test_identity_survives_when_customer_info_rebuilt(monkeypatch):
    """Turn 4 must still resolve with phone from previous brief if info lost."""
    class FakeStore:
        def update_session_customer_id(self, *_args):
            return None

    monkeypatch.setattr(input_nodes, "get_postgres_memory_store", lambda: FakeStore())

    # customer_info intentionally empty (simulates rebuilt dict on Turn 4);
    # phone/name only available in the previous CallBrief.
    state = {
        "messages": [HumanMessage(content="tư vấn giúp em tiếp đi")],
        "customer_id": None,
        "customer_info": {"channel": "web_chat", "_input_text": "tư vấn giúp em tiếp đi"},
        "call_brief": {
            "customer_id": "CUST-1029",
            "customer_phone": "0912345678",
            "customer_name": "An",
        },
    }
    state.update(normalize_input_node(state))
    resolved = resolve_identity_node(state)
    assert resolved["customer_id"] == "CUST-1029"
    assert resolved["customer_info"]["phone"] == "0912345678"
    assert resolved["customer_info"]["name"] == "An"
    assert resolved["needs_identity"] is False
