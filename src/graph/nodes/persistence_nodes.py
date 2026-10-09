"""Persist working-memory events and completed-session summaries."""

from __future__ import annotations

import ast
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, messages_to_dict

from src.graph.state import AgentState
from src.memory.profile.profile_store import get_profile_store
from src.memory.working.postgres_store import (
    PostgresMemoryStore,
    close_postgres_memory_store,
    get_postgres_memory_store,
)

_store: Optional[PostgresMemoryStore] = None


def get_working_memory_store() -> PostgresMemoryStore:
    """Return the process-wide PostgreSQL event and episode store."""
    global _store
    if _store is None:
        _store = get_postgres_memory_store()
    return _store


def close_working_memory_store() -> None:
    """Close the shared SQLAlchemy engine during application shutdown."""
    global _store
    _store = None
    close_postgres_memory_store()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))
    return str(value)


def _parse_tool_result(content: Any) -> Any:
    if isinstance(content, (dict, list)):
        return _json_safe(content)
    if not isinstance(content, str):
        return _json_safe(content)
    try:
        return _json_safe(json.loads(content))
    except json.JSONDecodeError:
        try:
            return _json_safe(ast.literal_eval(content))
        except (ValueError, SyntaxError):
            return content


def _current_turn_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    latest_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        0,
    )
    return messages[latest_user_index:]


def _tool_calls(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    calls = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        calls.extend(
            {
                "id": call.get("id"),
                "name": call.get("name"),
                "args": _json_safe(call.get("args", {})),
            }
            for call in message.tool_calls
        )
    return calls


def _tool_results(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    return [
        {
            "name": message.name,
            "tool_call_id": message.tool_call_id,
            "result": _parse_tool_result(message.content),
        }
        for message in messages
        if isinstance(message, ToolMessage)
    ]


def _identity_snapshot(state: AgentState) -> Dict[str, Any]:
    customer_info = state.get("customer_info") or {}
    fields = ("phone", "name", "honorific", "channel", "zalo_id", "fb_id", "identities")
    identity = {key: customer_info[key] for key in fields if key in customer_info}
    if state.get("customer_id"):
        identity["customer_id"] = state["customer_id"]
    return _json_safe(identity)


def persist_turn_node(state: AgentState) -> Dict[str, Any]:
    """Append this turn's transcript, tool activity, identity, and status to PostgreSQL."""
    now = datetime.now(timezone.utc).isoformat()
    session_id = state.get("session_id") or str(uuid.uuid4())
    turn_id = state.get("turn_id") or str(uuid.uuid4())
    turn_messages = _current_turn_messages(state.get("messages", []))
    results = _tool_results(turn_messages)
    tool_handoff = any(item["name"] == "handoff.transfer" for item in results)

    payload = {
        "messages": _json_safe(messages_to_dict(turn_messages)),
        "identity": _identity_snapshot(state),
        "tool_calls": _tool_calls(turn_messages),
        "tool_results": results,
        "call_brief": _json_safe(state.get("call_brief") or {}),
        "status": {
            "input_valid": state.get("input_valid"),
            "output_valid": state.get("output_valid"),
            "guardrail_feedback": state.get("guardrail_feedback"),
            "is_handoff": bool(state.get("is_handoff") or tool_handoff),
            "handoff_reason": state.get("handoff_reason"),
            "session_ended": bool(state.get("session_ended", False)),
            "session_outcome": state.get("session_outcome"),
        },
    }
    turn_number = get_working_memory_store().append_turn(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        turn_id=turn_id,
        customer_id=state.get("customer_id"),
        created_at=now,
        payload=payload,
    )
    return {
        "session_id": session_id,
        "session_started_at": state.get("session_started_at") or now,
        "turn_id": turn_id,
        "turn_number": turn_number,
        "is_handoff": bool(state.get("is_handoff") or tool_handoff),
    }


def _successful_profile_updates(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    updates: Dict[str, Dict[str, Any]] = {}
    for event in events:
        payload = event["payload"]
        calls = {call.get("id"): call for call in payload.get("tool_calls", [])}
        for result in payload.get("tool_results", []):
            if result.get("name") != "memory.write":
                continue
            call = calls.get(result.get("tool_call_id"))
            output = result.get("result")
            if not call or not isinstance(output, dict):
                continue
            if output.get("status") not in {"success", "queued_for_session_commit"}:
                continue
            args = call.get("args") or {}
            key = args.get("key")
            if isinstance(key, str) and key.strip() and "value" in args:
                updates[key] = {"key": key, "value": args["value"]}
    return list(updates.values())


def _episode_from_events(events: List[Dict[str, Any]], state: AgentState) -> Dict[str, Any]:
    products: Dict[str, Dict[str, Any]] = {}
    callbacks = []
    orders = []
    profile_updates = _successful_profile_updates(events)
    handoff = bool(state.get("is_handoff"))
    call_brief = state.get("call_brief") or {}

    for event in events:
        payload = event["payload"]
        calls = {call.get("id"): call for call in payload.get("tool_calls", [])}
        for result in payload.get("tool_results", []):
            name = result.get("name")
            output = result.get("result")
            if not isinstance(output, dict):
                continue
            call = calls.get(result.get("tool_call_id"), {})
            args = call.get("args") or {}

            if name == "catalog.search":
                for item in output.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    sku = item.get("sku")
                    if sku:
                        products.setdefault(
                            sku,
                            {"sku": sku, "name": item.get("name")},
                        )
            elif name == "pricing.get_quote":
                sku = args.get("sku")
                if sku:
                    product = products.setdefault(sku, {"sku": sku})
                    product["price_quoted_vnd"] = output.get("final_price_vnd")
                    product["applied_promos"] = output.get("applied_promos", [])
            elif name == "inventory.check":
                sku = args.get("sku") or output.get("sku")
                if sku:
                    products.setdefault(sku, {"sku": sku})["in_stock"] = output.get(
                        "in_stock"
                    )
            elif name == "schedule.callback":
                callbacks.append(
                    {
                        "callback_at": args.get("callback_at"),
                        "note": args.get("note"),
                        "callback_id": output.get("callback_id"),
                    }
                )
            elif name == "order.create":
                orders.append(output)
            elif name == "handoff.transfer":
                handoff = True

    outcome = state.get("session_outcome")
    if not outcome:
        if handoff:
            outcome = "handed_off"
        elif orders:
            outcome = "order_created"
        elif callbacks:
            outcome = "callback_scheduled"
        else:
            outcome = "completed"

    return {
        "products_advised": list(products.values()),
        "open_blockers": call_brief.get("open_blockers", []),
        "open_questions": call_brief.get("open_questions", []),
        "orders": orders,
        "callbacks": callbacks,
        "outcome": outcome,
        "summary": (
            "Tư vấn sản phẩm: "
            + ", ".join(product["sku"] for product in products.values())
            + "."
            if products
            else f"Phiên kết thúc với kết quả: {outcome}."
        ),
        "handoff_reason": state.get("handoff_reason"),
        "profile_facts_written": [fact["key"] for fact in profile_updates],
        "turn_count": len(events),
        "started_at": state.get("session_started_at"),
    }


def persist_call_node(state: AgentState) -> Dict[str, Any]:
    """Write completed-session episodic memory and explicit profile facts."""
    if not state.get("session_ended", False):
        return {}

    session_id = state.get("session_id")
    customer_id = state.get("customer_id")
    if not session_id:
        raise ValueError("session_id is required to persist a completed call.")

    store = get_working_memory_store()
    events = store.get_session_events(session_id)
    if not events:
        raise RuntimeError(f"No working-memory events found for session {session_id}.")

    episode = _episode_from_events(events, state)
    episode["channel"] = (state.get("customer_info") or {}).get("channel")
    ended_at = datetime.now(timezone.utc).isoformat()
    store.save_episode(
        session_id=session_id,
        customer_id=customer_id,
        ended_at=ended_at,
        payload=episode,
    )

    profile_updates = _successful_profile_updates(events)
    if customer_id and profile_updates:
        get_profile_store().add_profile_facts(
            customer_id=customer_id,
            facts=profile_updates,
            session_id=session_id,
        )

    return {}
