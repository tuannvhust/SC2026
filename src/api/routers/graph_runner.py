"""Prepare API turns with persisted session context and invoke the graph."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import date
from typing import Any, Callable, Dict, Optional, cast

from langchain_core.messages import HumanMessage, messages_from_dict

from src.graph.builder import graph
from src.graph.state import AgentState
from src.graph.trace import (
    GraphTrace,
    append_eval_trace_line,
    build_eval_trace_record,
    new_run_id,
)
from src.memory.working.postgres_store import get_postgres_memory_store

logger = logging.getLogger(__name__)


def _restore_identity_from_events(events) -> Dict[str, Any]:
    """Restore guest identity + ask attempts across stateless API turns.

    Iterates events in order (oldest → newest) so later events override earlier
    ones for mutable fields (attempts, missing_fields, pending_need).
    Identity contact fields (phone, name, honorific) use first-seen semantics
    so a phone captured in Turn 1 is not lost in Turn 2.
    """
    restored: Dict[str, Any] = {}
    attempts = 0
    restored_customer_id: Optional[str] = None
    # missing_fields and pending_need: latest-event wins (most up-to-date state).
    missing: list = []
    pending_need: Optional[str] = None
    for event in events or []:
        payload = event.get("payload", {}) if isinstance(event, dict) else {}
        identity = payload.get("identity", {}) if isinstance(payload, dict) else {}
        if not isinstance(identity, dict):
            continue
        # Contact fields: first-seen wins (preserve a phone/name from Turn 1).
        for key in ("phone", "name", "honorific", "zalo_id", "fb_id"):
            value = identity.get(key)
            if value and key not in restored:
                restored[key] = value
        # Customer ID: first resolved wins.
        if identity.get("customer_id") and not restored_customer_id:
            restored_customer_id = identity["customer_id"]
        # Attempts: highest seen across all events.
        attempts = max(attempts, int(identity.get("identity_attempts") or 0))
        # Missing fields / pending_need: latest event overrides earlier ones.
        if identity.get("missing_identity_fields") is not None:
            missing = list(identity["missing_identity_fields"])
        if identity.get("pending_need"):
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
    call_date: Optional[date] = None,
    customer_info: Optional[Dict[str, Any]] = None,
    session_ended: bool = False,
    on_call_brief: Optional[Callable[[Dict[str, Any]], None]] = None,
    eval_trace_context: Optional[Dict[str, Any]] = None,
    eval_trace_path: Optional[str] = None,
) -> Dict[str, Any]:
    turn_started_at = time.perf_counter()
    active_session_id = session_id or str(uuid.uuid4())
    requested_customer_id = (
        customer_id if customer_id and customer_id != "anonymous" else None
    )
    memory_store = get_postgres_memory_store()
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

    try:
        effective_customer_id = memory_store.ensure_session(
            session_id=active_session_id,
            customer_id=requested_customer_id,
            channel=normalized_channel,
        )
    except Exception as error:
        logger.exception(
            "Could not ensure conversation session %s before graph execution.",
            active_session_id,
        )
        raise RuntimeError(
            "Could not create or confirm the conversation session."
        ) from error

    events = memory_store.get_session_events(
        active_session_id,
        customer_id=effective_customer_id,
        unassigned_only=not effective_customer_id,
        limit=20,
    )
    history = []
    if not getattr(graph, "checkpointer_enabled", False):
        for event in events:
            serialized_messages = event.get("payload", {}).get("messages", [])
            if serialized_messages:
                history.extend(messages_from_dict(serialized_messages))

    _restored = _restore_identity_from_events(events)

    initial_state = {
        "messages": [*history, HumanMessage(content=message)],
        "customer_id": effective_customer_id or _restored.get("customer_id"),
        "customer_info": {
            **_restored.get("customer_info_patch", {}),
            **(customer_info or {}),
            "channel": normalized_channel,
        },
        "identity_attempts": _restored.get("identity_attempts", 0),
        "missing_identity_fields": _restored.get("missing_identity_fields", []),
        "pending_need": _restored.get("pending_need"),
        "session_id": active_session_id,
        "call_date": (call_date or date(2026, 10, 15)).isoformat(),
        "turn_id": turn_id or str(uuid.uuid4()),
        "session_ended": session_ended,
    }
    if getattr(graph, "checkpointer_enabled", False):
        stream_config = {"configurable": {"thread_id": active_session_id}}
    else:
        stream_config = None

    run_id = new_run_id()
    from src.graph.tool_observer import set_run_context
    set_run_context(run_id=run_id, session_id=active_session_id, turn_id=turn_id or "")

    trace = GraphTrace(run_id=run_id, session_id=active_session_id, turn_id=turn_id)
    trace.run_start(
        mode="api_turn",
        channel=normalized_channel,
        checkpointer=bool(getattr(graph, "checkpointer_enabled", False)),
        thread=active_session_id,
    )
    final_state: Optional[Dict[str, Any]] = None

    last_emitted_brief = None
    try:
        for mode, payload in graph.stream(
            initial_state,
            stream_config,
            stream_mode=["values", "debug"],
        ):
            if mode == "values" and isinstance(payload, dict):
                final_state = cast(Dict[str, Any], payload)
                current_brief = final_state.get("call_brief")
                if (
                    on_call_brief
                    and isinstance(current_brief, dict)
                    and current_brief != last_emitted_brief
                ):
                    on_call_brief(current_brief)
                    last_emitted_brief = current_brief
            elif mode == "debug":
                trace.debug_event(payload)
    except Exception as error:
        trace.run_failed(error)
        raise
    trace.run_end(status="success")
    if final_state is None:
        # Parity with the previous invoke() behaviour on an empty stream.
        final_state = initial_state
    if eval_trace_context is not None and eval_trace_path:
        total_ms = int((time.perf_counter() - turn_started_at) * 1000)
        row = build_eval_trace_record(
            state=final_state,
            run_id=run_id,
            total_ms=total_ms,
            context=eval_trace_context,
        )
        append_eval_trace_line(row, eval_trace_path)
    return final_state


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
    stored_customer_id = store.get_session_customer_id(active_session_id)
    requested_customer_id = (
        customer_id if customer_id and customer_id != "anonymous" else None
    )
    if (
        requested_customer_id
        and stored_customer_id
        and requested_customer_id != stored_customer_id
    ):
        raise ValueError("The session is associated with a different customer.")
    restored_customer_id = requested_customer_id or stored_customer_id
    events = store.get_session_events(
        active_session_id,
        customer_id=restored_customer_id,
        limit=1000,
        unassigned_only=not restored_customer_id,
    )
    if not restored_customer_id and events:
        for event in reversed(events):
            candidate = event.get("customer_id")
            if candidate:
                restored_customer_id = candidate
                break

    trace = GraphTrace(
        run_id=new_run_id(),
        session_id=active_session_id,
        turn_id=None,
    )
    trace.run_start(mode="finalize", thread=active_session_id)

    state: AgentState = {
        "messages": [],
        "session_id": active_session_id,
        "customer_id": restored_customer_id,
        "customer_info": dict(customer_info or {}),
        "session_ended": True,
    }
    result = persist_call_node(state) or {}
    episode = store.get_episode(active_session_id)
    if result.get("already_finalized"):
        finalize_status = "already_finalized"
    elif result.get("empty_session"):
        finalize_status = "empty_session"
    elif result.get("finalized"):
        finalize_status = "finalized"
    else:
        finalize_status = "failed"
    trace.finalize(
        status=finalize_status,
        working_events=result.get("working_events"),
        episode=episode is not None,
        already_finalized=bool(result.get("already_finalized")),
        empty_session=bool(result.get("empty_session")),
        profile_facts_written=result.get("profile_facts_written"),
        warning=result.get("persistence_warning"),
    )
    profile_facts: Dict[str, Any] = {}
    if restored_customer_id:
        try:
            from src.memory.profile.profile_store import get_profile_store

            profile_facts = get_profile_store().get_profile_facts(restored_customer_id)
            trace._emit(f"[memory] profile_read facts={len(profile_facts)} (read-only)")
        except Exception as error:
            trace._emit(
                f"[memory] profile_read failed error={type(error).__name__}",
                logging.WARNING,
            )
            logger.warning(
                "profile read-back failed for session %s: %s",
                active_session_id,
                error,
                exc_info=True,
            )
    trace.run_end(status="finalized")
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
                "call_brief": _public_call_brief(result.get("call_brief")),
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
        "call_brief": _public_call_brief(result.get("call_brief")),
    }


def _public_call_brief(call_brief: Any) -> Optional[Dict[str, Any]]:
    """Expose only the conversation summary needed by the chat UI."""
    if not isinstance(call_brief, dict):
        return None
    recent_sessions = []
    for session in call_brief.get("recent_sessions") or []:
        if not isinstance(session, dict):
            continue
        recent_sessions.append(
            {
                "date": str(session.get("date") or "")[:32],
                "summary": str(session.get("summary") or "")[:300],
                "outcome": str(session.get("outcome") or "")[:80],
            }
        )
    memory_sources = call_brief.get("memory_sources") or {}
    profile_sources = memory_sources.get("profile_facts", {})
    has_history = bool(
        recent_sessions
        or call_brief.get("current_session_history")
        or profile_sources
    )
    return {
        "status": call_brief.get("memory_status", "empty"),
        "has_history": has_history,
        "current_need": str(call_brief.get("current_need") or "")[:500],
        "recent_sessions": recent_sessions[:3],
        "open_blockers": [
            str(item)[:200]
            for item in (call_brief.get("open_blockers") or [])[:5]
            if isinstance(item, str)
        ],
        "open_questions": [
            str(item)[:200]
            for item in (call_brief.get("open_questions") or [])[:5]
            if isinstance(item, str)
        ],
        "suggested_next_action": str(
            call_brief.get("suggested_next_action") or ""
        )[:300],
    }
