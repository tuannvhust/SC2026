import json
from datetime import datetime
from typing import Any, Dict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .edges import (
    route_after_guardrail,
    route_after_guardrail_failure,
    route_after_plan,
    route_after_tool,
)
from .guardrails import guardrail_check
from .llm import real_llm_text, use_fake_llm
from .memory import db, init_db
from .nodes import (
    build_call_brief,
    call_tool,
    handle_guardrail_failure,
    handoff_to_human,
    input_normalize,
    persist_turn,
    plan_step,
    resolve_identity,
    retrieve_context,
    trace_emit,
)
from .state import CallState


def build_graph():
    """Khởi tạo SQLite database, kết nối các node và conditional edge, sau đó compile graph."""
    init_db()
    b = StateGraph(CallState)
    for name, fn in [
        ("resolve_identity", resolve_identity),
        ("build_call_brief", build_call_brief),
        ("input_normalize", input_normalize),
        ("retrieve_context", retrieve_context),
        ("plan_step", plan_step),
        ("call_tool", call_tool),
        ("guardrail_check", guardrail_check),
        ("handle_guardrail_failure", handle_guardrail_failure),
        ("handoff_to_human", handoff_to_human),
        ("persist_turn", persist_turn),
        ("trace_emit", trace_emit),
    ]:
        b.add_node(name, fn)

    b.add_edge(START, "resolve_identity")
    b.add_edge("resolve_identity", "build_call_brief")
    b.add_edge("build_call_brief", "input_normalize")
    b.add_edge("input_normalize", "retrieve_context")
    b.add_edge("retrieve_context", "plan_step")
    b.add_conditional_edges(
        "plan_step",
        route_after_plan,
        {
            "handoff_to_human": "handoff_to_human",
            "call_tool": "call_tool",
            "guardrail_check": "guardrail_check",
        },
    )
    b.add_conditional_edges(
        "call_tool",
        route_after_tool,
        {
            "handoff_to_human": "handoff_to_human",
            "guardrail_check": "guardrail_check",
            "plan_step": "plan_step",
        },
    )
    b.add_conditional_edges(
        "guardrail_check",
        route_after_guardrail,
        {
            "persist_turn": "persist_turn",
            "handle_guardrail_failure": "handle_guardrail_failure",
        },
    )
    b.add_conditional_edges(
        "handle_guardrail_failure",
        route_after_guardrail_failure,
        {
            "handoff_to_human": "handoff_to_human",
            "plan_step": "plan_step",
        },
    )
    b.add_edge("handoff_to_human", "persist_turn")
    b.add_edge("persist_turn", "trace_emit")
    b.add_edge("trace_emit", END)
    return b.compile(checkpointer=MemorySaver())


def handle_customer_turn(
    graph, call_id: str, customer_phone: str, channel: str, user_message: str,
    *, call_date: str = "2026-10-15", scenario_id: str = "local", call: str = "call_1",
    turn: int = 1, input_mode: str = "clean", channel_identity: str | None = None,
    config: str = "full", trace_path: str | None = None
) -> Dict[str, Any]:
    """thread_id = call_id: LangGraph lưu giữ lịch sử cuộc gọi NÀY; bộ nhớ khách hàng dài hạn nằm trong SQLite."""
    return graph.invoke(
        {
            # Reset trạng thái theo từng lượt (nếu không checkpointer sẽ giữ lại cờ và dữ liệu từ lượt trước)
            "customer_phone": customer_phone,
            "channel": channel,
            "call_id": call_id,
            "scenario_id": scenario_id, "config": config, "call": call, "turn": turn,
            "call_date": call_date, "input_mode": input_mode,
            "channel_identity": channel_identity, "trace_path": trace_path,
            "raw_customer_text": user_message, "run_id": f"{scenario_id}-{config}",
            "messages": [{"role": "user", "content": user_message}],
            "tool_results": [],
            "tool_calls": [],
            "tool_call_count": 0,
            "retry_count": 0,
            "needs_handoff": False,
            "handoff_reason": None,
            "handoff_brief": None,
            "guardrail_passed": False,
            "guardrail_violation_reason": None,
            "draft_response": None,
            "final_response": None,
            "facts_to_persist": {},
            "max_tool_calls": 3,
            "max_retries": 2,
            "working_memory": {}, "long_term_facts": {}, "facts_used": [],
            "questions": [], "claims": [], "memory_writes": [],
            "latency": {"ttft_ms": 0, "total_ms": 0, "ttfa_ms": None},
        },
        config={"configurable": {"thread_id": call_id}, "recursion_limit": 25},
    )


def finalize_call(graph, call_id: str) -> str:
    """Gọi khi cuộc gọi kết thúc. Ghi lại MỘT bản tóm tắt phân đoạn (episodic summary) cho toàn bộ cuộc gọi."""
    values = graph.get_state({"configurable": {"thread_id": call_id}}).values
    cid, msgs = values.get("customer_id"), values.get("messages", [])
    outcome = values.get("call_outcome") or "hen_lai"
    if use_fake_llm():
        user_lines = [m["content"] for m in msgs if m["role"] == "user"]
        summary = f"Khách nói: {' | '.join(user_lines)[:200]}. Kết quả: {outcome}."
    else:  # ĐÁNH GIÁ: câu prompt tóm tắt cuộc gọi
        summary = real_llm_text(
            "Tóm tắt cuộc gọi bán hàng trong 1-2 câu tiếng Việt: sản phẩm, giá đã báo, rào cản, kết quả.",
            json.dumps(msgs, ensure_ascii=False),
        )
    with db() as c:
        c.execute(
            "INSERT INTO episodic(customer_id,call_id,ts,summary,outcome) VALUES (?,?,?,?,?)",
            (cid, call_id, datetime.now().isoformat(), summary, outcome),
        )
    return summary
