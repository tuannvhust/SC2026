"""Graph trace logging: format, sanitization, and API runner integration."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import src.graph.trace as trace_mod
from src.api.routers import graph_runner
from src.graph.trace import GraphTrace, new_run_id, sanitize


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def _capture():
    handler = _Capture()
    trace_mod.LOGGER.addHandler(handler)
    return handler


def _task(name, step=1, ts="2026-10-17T00:00:00+00:00", triggers=None):
    payload = {"name": name}
    if triggers is not None:
        payload["triggers"] = triggers
    return {"type": "task", "step": step, "timestamp": ts, "payload": payload}


def _task_result(name, step=1, ts="2026-10-17T00:00:00.500000+00:00", result=None, error=None):
    return {
        "type": "task_result",
        "step": step,
        "timestamp": ts,
        "payload": {"name": name, "result": result, "error": error},
    }


def test_trace_node_pair_uses_real_timestamps_and_format():
    handler = _capture()
    trace = GraphTrace(run_id="abc123", session_id="s-1", turn_id="t-1")
    trace.run_start(mode="api_turn", channel="web_chat", checkpointer=True, thread="s-1")
    trace.debug_event(_task("input_guardrail"))
    trace.debug_event(_task_result("input_guardrail", result={"input_valid": True}))
    trace.run_end(status="success")
    trace_mod.LOGGER.removeHandler(handler)

    text = "\n".join(handler.lines)
    assert "[GRAPH][run=abc123] START mode=api_turn channel=web_chat" in text
    assert "[node=input_guardrail] START step=1" in text
    assert "[node=input_guardrail] END status=success duration_ms=500" in text
    assert "summary=input_valid=True" in text
    assert "END status=success" in text


def test_trace_masks_phone_and_secrets():
    masked = sanitize("gọi 0912345678 với api_key=SECRET123 token: abc", limit=200)
    assert "0912345678" not in masked
    assert "SECRET123" not in masked
    assert "0***" in masked
    assert "api_key=***" in masked
    long = sanitize("x" * 500, limit=50)
    assert len(long) <= 60
    assert long.endswith("...(cut)")


def test_trace_silent_level_emits_nothing():
    handler = _capture()
    trace = GraphTrace(run_id="silent-run", level="silent")
    trace.run_start(mode="api_turn")
    trace.debug_event(_task("plan_step"))
    trace.run_end()
    trace_mod.LOGGER.removeHandler(handler)
    assert handler.lines == []


def test_run_failed_logs_dangling_node_then_run_end_error():
    handler = _capture()
    trace = GraphTrace(run_id="fail01")
    trace.run_start(mode="api_turn")
    trace.debug_event(_task("plan_step"))
    trace.run_failed(RuntimeError("planner down"))
    trace_mod.LOGGER.removeHandler(handler)

    text = "\n".join(handler.lines)
    assert "[node=plan_step] END status=failed" in text
    assert "END status=failed" in text
    assert "RuntimeError: planner down" in text


def test_tools_summary_separates_error_from_empty_success():
    handler = _capture()
    trace = GraphTrace(run_id="tool01")
    error_msg = ToolMessage(
        name="inventory.check",
        content='{"sku": "X", "status": "error", "error_code": "supabase_unavailable"}',
        tool_call_id="t1",
        status="error",
    )
    empty_ok = ToolMessage(
        name="catalog.search",
        content='{"items": []}',
        tool_call_id="t2",
    )
    trace.debug_event(
        _task_result("tools", result={"messages": [error_msg, empty_ok]})
    )
    trace_mod.LOGGER.removeHandler(handler)

    text = "\n".join(handler.lines)
    assert "tool=inventory.check status=error code=supabase_unavailable" in text
    assert "tool=catalog.search status=success results=0" in text
    # Empty result must not be reported as an error.
    assert "tool=catalog.search status=error" not in text


def test_invoke_customer_turn_streams_trace_and_returns_final_values(monkeypatch):
    monkeypatch.setattr(
        graph_runner,
        "get_postgres_memory_store",
        lambda: SimpleNamespace(
            ensure_session=lambda **kwargs: kwargs["customer_id"],
            get_session_customer_id=lambda _sid: None,
            get_session_events=lambda _sid, **_kwargs: [],
        ),
    )
    captured = {}

    def stream(state, config, stream_mode=None):
        captured["state"] = state
        captured["config"] = config
        captured["stream_mode"] = stream_mode
        final = {
            **state,
            "messages": [*state["messages"], AIMessage(content="Answer.")],
            "turn_number": 2,
        }
        yield ("values", final)
        yield ("debug", _task("input_guardrail"))
        yield (
            "debug",
            _task_result("input_guardrail", result={"input_valid": True}),
        )

    monkeypatch.setattr(graph_runner, "graph", SimpleNamespace(stream=stream))
    handler = _capture()
    state = graph_runner.invoke_customer_turn(
        customer_id="customer-1",
        session_id="session-trace",
        turn_id="turn-trace",
        message="Gọi tôi 0912345678",
        channel="chat",
    )
    trace_mod.LOGGER.removeHandler(handler)

    # Response semantics unchanged: last values payload, same as invoke() gave.
    assert state["messages"][-1].content == "Answer."
    assert state["turn_number"] == 2
    assert graph_runner.response_from_graph(state)["reply"] == "Answer."
    assert captured["stream_mode"] == ["values", "debug"]

    text = "\n".join(handler.lines)
    assert "[GRAPH][run=" in text
    assert "mode=api_turn" in text
    assert "[node=input_guardrail] END status=success duration_ms=500" in text
    assert "END status=success" in text
    # PII from the user message must never reach the trace.
    assert "0912345678" not in text
    # Single run id across all lines of this run.
    run_ids = {line.split("run=")[1].split("]")[0] for line in handler.lines if "run=" in line}
    assert len(run_ids) == 1


def test_invoke_customer_turn_logs_failure_before_reraise(monkeypatch):
    monkeypatch.setattr(
        graph_runner,
        "get_postgres_memory_store",
        lambda: SimpleNamespace(
            ensure_session=lambda **kwargs: kwargs["customer_id"],
            get_session_customer_id=lambda _sid: None,
            get_session_events=lambda _sid, **_kwargs: [],
        ),
    )

    def stream(state, config, stream_mode=None):
        yield ("debug", _task("plan_step"))
        raise RuntimeError("LLM exploded")

    monkeypatch.setattr(graph_runner, "graph", SimpleNamespace(stream=stream))
    handler = _capture()
    with pytest.raises(RuntimeError, match="LLM exploded"):
        graph_runner.invoke_customer_turn(
            customer_id=None,
            session_id="session-fail",
            turn_id="turn-fail",
            message="hi",
            channel="chat",
        )
    trace_mod.LOGGER.removeHandler(handler)

    text = "\n".join(handler.lines)
    # The node started before the crash is still reported, then the run error.
    assert "[node=plan_step] START" in text
    assert "[node=plan_step] END status=failed" in text
    assert "END status=failed" in text
    assert "LLM exploded" in text


def test_finalize_session_emits_finalize_trace(monkeypatch):
    from src.graph.nodes import persistence_nodes
    from src.memory.profile import profile_store as profile_store_mod

    store = SimpleNamespace(
        ensure_session=lambda **kwargs: kwargs["customer_id"],
        get_session_customer_id=lambda _sid: None,
        get_session_events=lambda _sid, **_kwargs: [{"customer_id": "CUST-1"}],
        get_episode=lambda _sid: {"outcome": "completed"},
    )
    monkeypatch.setattr(graph_runner, "get_postgres_memory_store", lambda: store)
    # finalize_session imports these locally at call time: patch the source modules.
    monkeypatch.setattr(
        persistence_nodes,
        "persist_call_node",
        lambda state: {
            "finalized": True,
            "already_finalized": False,
            "working_events": 2,
            "episode_outcome": "completed",
            "profile_facts_written": ["budget"],
        },
    )
    monkeypatch.setattr(
        profile_store_mod,
        "get_profile_store",
        lambda: SimpleNamespace(get_profile_facts=lambda _cid: {"budget": "5tr"}),
    )
    handler = _capture()
    result = graph_runner.finalize_session(session_id="session-fin")
    trace_mod.LOGGER.removeHandler(handler)

    assert result["finalized"] is True
    text = "\n".join(handler.lines)
    assert "mode=finalize" in text
    assert "FINALIZE status=finalized working_events=2 episode=yes" in text
    assert "profile_facts_written=1" in text
    assert "profile_read facts=1 (read-only)" in text
    assert "END status=finalized" in text
