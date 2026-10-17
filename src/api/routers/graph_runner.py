"""Prepare API turns with persisted session context and invoke the graph."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, messages_from_dict

from src.graph.builder import graph
from src.memory.working.postgres_store import get_postgres_memory_store

logger = logging.getLogger(__name__)


def _restore_identity_from_events(events) -> Dict[str, Any]:
    """Restore guest identity + ask attempts across stateless API turns."""
    restored: Dict[str, Any] = {}
    attempts = 0
    restored_customer_id: Optional[str] = None
    missing: list = []
    pending_need: Optional[str] = None
    for event in events or []:
        payload = event.get("payload", {}) if isinstance(event, dict) else {}
        identity = payload.get("identity", {}) if isinstance(payload, dict) else {}
        if not isinstance(identity, dict):
            continue
        for key in ("phone", "name", "honorific", "zalo_id", "fb_id"):
            value = identity.get(key)
            if value and key not in restored:
                restored[key] = value
        if identity.get("customer_id") and not restored_customer_id:
            restored_customer_id = identity["customer_id"]
        attempts = max(attempts, int(identity.get("identity_attempts") or 0))
        if identity.get("missing_identity_fields") and not missing:
            missing = list(identity["missing_identity_fields"])
        if identity.get("pending_need") and not pending_need:
            pending_need = identity["pending_need"]
    return {
        "customer_info_patch": restored,
        "identity_attempts": attempts,
        "customer_id": restored_customer_id,
        "missing_identity_fields": missing,
        "pending_need": pending_need,
    }


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

    _restored = _restore_identity_from_events(events)

    initial_state = {
        "messages": [*history, HumanMessage(content=message)],
        "customer_id": customer_id or _restored.get("customer_id"),
        "customer_info": {
            **_restored.get("customer_info_patch", {}),
            **(customer_info or {}),
            "channel": normalized_channel,
        },
        "identity_attempts": _restored.get("identity_attempts", 0),
        "missing_identity_fields": _restored.get("missing_identity_fields", []),
        "pending_need": _restored.get("pending_need"),
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


def finalize_session(
    *,
    session_id: str,
    customer_id: Optional[str] = None,
    customer_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Finalize a session without fake messages or extra LLM calls.

    Reads persisted working events, builds the episode + profile commit via
    ``persist_call_node`` and returns the real persistence status so the
    frontend only reports success after the backend confirms it.
    """
    from src.graph.nodes.persistence_nodes import persist_call_node

    active_session_id = (session_id or "").strip()
    if not active_session_id:
        raise ValueError("session_id is required to finalize a session.")

    store = get_postgres_memory_store()
    events = store.get_session_events(active_session_id)
    restored_customer_id = customer_id
    if not restored_customer_id and events:
        for event in reversed(events):
            candidate = event.get("customer_id")
            if candidate:
                restored_customer_id = candidate
                break

    state: Dict[str, Any] = {
        "messages": [],
        "session_id": active_session_id,
        "customer_id": restored_customer_id,
        "customer_info": dict(customer_info or {}),
        "session_ended": True,
    }
    result = persist_call_node(state) or {}
    episode = store.get_episode(active_session_id)
    profile_facts: Dict[str, Any] = {}
    if restored_customer_id:
        try:
            from src.memory.profile.profile_store import get_profile_store

            profile_facts = get_profile_store().get_profile_facts(restored_customer_id)
        except Exception as error:
            logger.warning(
                "profile read-back failed for session %s: %s",
                active_session_id,
                error,
                exc_info=True,
            )
    return {
        "session_id": active_session_id,
        "customer_id": restored_customer_id,
        "finalized": bool(result.get("finalized", False)),
        "already_finalized": bool(result.get("already_finalized", False)),
        "empty_session": bool(result.get("empty_session", False)),
        "working_events": int(result.get("working_events", len(events or []))),
        "episode": episode,
        "episode_outcome": result.get("episode_outcome")
        or (episode or {}).get("outcome"),
        "profile_facts_written": result.get("profile_facts_written", []),
        "profile_facts": profile_facts,
        "persistence_warning": result.get("persistence_warning"),
    }


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
