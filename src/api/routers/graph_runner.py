"""Prepare API turns with persisted session context and invoke the graph."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, messages_from_dict

from src.graph.builder import graph
from src.memory.working.postgres_store import get_postgres_memory_store


def invoke_customer_turn(
    *,
    customer_id: Optional[str],
    session_id: Optional[str],
    turn_id: Optional[str],
    message: str,
    channel: str,
    customer_info: Optional[Dict[str, Any]] = None,
    session_ended: bool = False,
) -> Dict[str, Any]:
    active_session_id = session_id or str(uuid.uuid4())
    events = get_postgres_memory_store().get_session_events(active_session_id)
    history = []
    if not getattr(graph, "checkpointer_enabled", False):
        for event in events:
            serialized_messages = event.get("payload", {}).get("messages", [])
            if serialized_messages:
                history.extend(messages_from_dict(serialized_messages))

    channel_aliases = {
        "chat": "web_chat",
        "call": "hotline",
        "facebook": "chat_fanpage",
        "zalo": "zalo_oa",
    }
    normalized_channel = channel_aliases.get(channel, channel)
    if normalized_channel not in {
        "hotline",
        "chat_fanpage",
        "zalo_oa",
        "web_chat",
        "other",
    }:
        normalized_channel = "other"

    initial_state = {
        "messages": [*history, HumanMessage(content=message)],
        "customer_id": customer_id,
        "customer_info": {**(customer_info or {}), "channel": normalized_channel},
        "session_id": active_session_id,
        "turn_id": turn_id or str(uuid.uuid4()),
        "session_ended": session_ended,
    }
    if getattr(graph, "checkpointer_enabled", False):
        return graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": active_session_id}},
        )
    return graph.invoke(initial_state)


def response_from_graph(result: Dict[str, Any]) -> Dict[str, Any]:
    messages = result.get("messages", [])
    final_ai_message = next(
        (
            message
            for message in reversed(messages)
            if getattr(message, "type", None) == "ai"
            and getattr(message, "content", None)
        ),
        None,
    )
    if final_ai_message is None:
        if result.get("input_valid") is False:
            return {
                "reply": "Dạ em chưa thể xử lý nội dung này. Em sẽ chuyển yêu cầu để nhân viên hỗ trợ ạ.",
                "session_id": result.get("session_id"),
                "turn_id": result.get("turn_id"),
                "turn_number": result.get("turn_number"),
                "is_handoff": bool(result.get("is_handoff", False)),
                "handoff_reason": result.get("handoff_reason"),
            }
        raise RuntimeError("Graph completed without a customer-facing AI response.")

    content = final_ai_message.content
    if isinstance(content, str):
        reply = content
    elif isinstance(content, list):
        reply = " ".join(
            str(part["text"])
            for part in content
            if isinstance(part, dict) and "text" in part
        )
    else:
        reply = str(content)
    if not reply.strip():
        raise RuntimeError("Graph returned an empty customer-facing response.")

    return {
        "reply": reply,
        "session_id": result.get("session_id"),
        "turn_id": result.get("turn_id"),
        "turn_number": result.get("turn_number"),
        "is_handoff": bool(result.get("is_handoff", False)),
        "handoff_reason": result.get("handoff_reason"),
    }
