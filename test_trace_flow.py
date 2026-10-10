import os
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langgraph_agent.src.graph import build_graph

def run_trace(user_msg: str, call_id: str = "test-call-trace-01"):
    graph = build_graph()
    phone = "0987654321"

    initial_state = {
        "customer_phone": phone,
        "channel": "voice_call",
        "call_id": call_id,
        "scenario_id": "trace_demo",
        "config": "full",
        "call": "call_1",
        "turn": 1,
        "call_date": "2026-10-15",
        "input_mode": "clean",
        "channel_identity": None,
        "trace_path": None,
        "raw_customer_text": user_msg,
        "run_id": "trace-test",
        "messages": [{"role": "user", "content": user_msg}],
        "tool_results": [],
        "pending_tool_results": [],
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
        "working_memory": {},
        "long_term_facts": {},
        "facts_used": [],
        "questions": [],
        "claims": [],
        "memory_writes": [],
        "latency": {"ttft_ms": 0, "total_ms": 0, "ttfa_ms": None},
        "call_ended": False,
    }

    print("=" * 70)
    print(f"BẮT ĐẦU TRACE: Input khách hàng = '{user_msg}'")
    print("=" * 70)

    step = 1
    for output in graph.stream(initial_state, config={"configurable": {"thread_id": call_id}}, stream_mode="updates"):
        for node_name, state_update in output.items():
            print(f"\n[BƯỚC {step}] ──> Node: {node_name}")
            step += 1
            for k, v in state_update.items():
                val_str = str(v)
                if len(val_str) > 160:
                    val_str = val_str[:160] + "... [còn tiếp]"
                print(f"      • {k}: {val_str}")

    print("\n" + "=" * 70)
    print("KẾT THÚC QUY TRÌNH")
    print("=" * 70)

if __name__ == "__main__":
    test_query = "Cho mình hỏi chính sách đổi trả sản phẩm bên shop như thế nào ạ?"
    run_trace(test_query)

