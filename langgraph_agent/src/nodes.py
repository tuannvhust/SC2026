import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime
from typing import Any, Dict

from .guardrails import guardrail_check
from .llm import fake_plan, real_llm_json, real_llm_text, use_fake_llm
from .memory import db, upsert_slot
from .prompts import PLAN_SYSTEM, format_plan_user_prompt
from .state import CallState
from .tools import CATALOG, TOOLS, tool_crm_get_customer

TOOL_TIMEOUT_S = 5
_executor = ThreadPoolExecutor(max_workers=4)


def resolve_identity(state: CallState) -> CallState:
    """Định danh khách hàng qua số điện thoại và tải dữ liệu profile, episodic từ SQLite."""
    data = tool_crm_get_customer(state["customer_phone"])
    return {**data, "call_id": state.get("call_id", "")}


def build_call_brief(state: CallState) -> CallState:
    """Xây dựng câu chào mở đầu tiếp nối cho khách hàng quay lại."""
    has_assistant_turn = any(m["role"] == "assistant" for m in state.get("messages", []))
    if not state.get("is_returning_customer") or has_assistant_turn:
        return {"call_brief": None}
    profile, episodic = state.get("profile", {}), state.get("episodic_summaries", [])
    if not profile and not episodic:
        return {"call_brief": None}

    # LƯU Ý: Câu mở đầu chủ động KHÔNG chứa bất kỳ con số giá nào. Giá bán luôn được
    # tra cứu lại từ catalog tool và được plan_step phát ngôn, tránh rò rỉ giá cũ từ bộ nhớ.
    facts_for_brief = {
        "product": CATALOG.get(profile.get("product_advised", ""), {}).get("name"),
        "blocker": profile.get("blocker"),
        "last_call": episodic[0]["summary"] if episodic else None,
    }
    if use_fake_llm():
        parts = ["Dạ em chào anh/chị,"]
        if facts_for_brief["product"]:
            parts.append(f"hôm trước bên em có tư vấn {facts_for_brief['product']}.")
        if facts_for_brief["blocker"]:
            parts.append("Anh/chị đã trao đổi với người nhà chưa ạ, hay còn băn khoăn điểm nào để em hỗ trợ thêm?")
        return {"call_brief": " ".join(parts)}
    # ĐÁNH GIÁ: Có thể tinh chỉnh câu prompt tiếng Việt theo phong cách bán hàng mong muốn
    return {
        "call_brief": real_llm_text(
            "Viết 1-2 câu mở đầu tiếng Việt (dạ/ạ) xác nhận tiếp nối cuộc gọi trước. KHÔNG nêu con số giá. "
            "KHÔNG hỏi lại thông tin đã biết. Chỉ dùng dữ kiện được cung cấp.",
            json.dumps(facts_for_brief, ensure_ascii=False),
        )
    }


def retrieve_context(state: CallState) -> CallState:
    """Node truy xuất ngữ cảnh tri thức: M1 là pass-through, sẵn sàng tích hợp RAG ở M2."""
    return {"retrieved_kb": state.get("retrieved_kb", [])}


def plan_step(state: CallState) -> CallState:
    """Node lập kế hoạch: quyết định hành động tiếp theo (gọi tool, trả lời, làm rõ, chuyển máy)."""
    try:
        out = (
            fake_plan(state)
            if use_fake_llm()
            else real_llm_json(PLAN_SYSTEM, format_plan_user_prompt(state))
        )
    except Exception:  # Lỗi cú pháp JSON / lỗi API -> fallback an toàn thay vì làm gián đoạn cuộc gọi
        return {"plan_action": "cannot_answer", "handoff_reason": "llm_error"}
    action = out.get("action", "cannot_answer")
    if action not in {"answer", "call_tool", "ask_clarify", "cannot_answer"}:
        action = "cannot_answer"
    upd: CallState = {
        "plan_action": action,
        "tool_calls": out.get("tool_calls", []) if action == "call_tool" else [],
        "draft_response": out.get("draft_response") if action in {"answer", "ask_clarify"} else None,
        "facts_to_persist": {**state.get("facts_to_persist", {}), **(out.get("facts") or {})},
    }
    if action == "cannot_answer":
        upd["handoff_reason"] = state.get("handoff_reason") or "cannot_answer"
    return upd


def call_tool(state: CallState) -> CallState:
    """Thực thi các lệnh gọi tool thông qua ThreadPoolExecutor và giám sát timeout."""
    results = list(state.get("tool_results", []))
    for tc in state.get("tool_calls", []):
        fn = TOOLS.get(tc.get("name"))
        if fn is None:
            return {"needs_handoff": True, "handoff_reason": "tool_error"}
        try:
            fut = _executor.submit(fn, **tc.get("args", {}))
            res = fut.result(timeout=TOOL_TIMEOUT_S)
        except FutureTimeout:
            return {"needs_handoff": True, "handoff_reason": "tool_timeout"}
        except Exception:
            return {"needs_handoff": True, "handoff_reason": "tool_error"}
        results.append({"tool": tc["name"], "args": tc.get("args", {}), "result": res})
    return {
        "tool_results": results,
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "tool_calls": [],
    }


def handle_guardrail_failure(state: CallState) -> CallState:
    """Xử lý khi vi phạm guardrail: tăng biến đếm retry và gửi cảnh báo nhắc nhở LLM."""
    n = state.get("retry_count", 0) + 1
    upd: CallState = {
        "retry_count": n,
        "draft_response": None,
        "plan_action": "answer",
        "messages": [
            {
                "role": "system",
                "content": f"Câu trả lời bị chặn: {state.get('guardrail_violation_reason')}. "
                "Chỉ dùng số liệu có trong tool_results.",
            }
        ],
    }
    if n >= state.get("max_retries", 2):
        upd["handoff_reason"] = "guardrail_exceeded"
    return upd


def handoff_to_human(state: CallState) -> CallState:
    """Chuyển giao cho tư vấn viên con người và ghi nhận câu hỏi chưa biết vào knowledge_gaps."""
    reason = state.get("handoff_reason") or "unknown"
    profile = state.get("profile", {})
    last_user = next(
        (m["content"] for m in reversed(state.get("messages", [])) if m["role"] == "user"), ""
    )
    brief = (
        f"[HANDOFF] Lý do: {reason}. Khách: {state.get('customer_id')}. "
        f"Câu cuối của khách: '{last_user}'. Profile: {json.dumps(profile, ensure_ascii=False)}."
    )
    if reason == "cannot_answer":  # Đưa câu hỏi vào Knowledge Gap Loop để đội ngũ bổ sung tri thức
        with db() as c:
            c.execute(
                "INSERT INTO knowledge_gaps(customer_id,call_id,question,ts) VALUES (?,?,?,?)",
                (
                    state.get("customer_id"),
                    state.get("call_id"),
                    last_user,
                    datetime.now().isoformat(),
                ),
            )
    return {
        "handoff_brief": brief,
        "final_response": (
            "Dạ để hỗ trợ mình chính xác nhất, em xin phép chuyển máy cho nhân viên chuyên trách ạ. "
            "Em là trợ lý AI và đã chuyển đầy đủ thông tin để mình không phải nhắc lại."
        ),
        "call_outcome": "chuyen_may",
    }


def persist_turn(state: CallState) -> CallState:
    """Lưu trữ dữ liệu của lượt thoại: cập nhật profile slot vào SQLite và lưu tin nhắn hoàn chỉnh."""
    final = state.get("final_response")
    if not final and state.get("guardrail_passed"):
        final = state.get("draft_response")
    facts = {k: v for k, v in (state.get("facts_to_persist") or {}).items()}
    cid = state.get("customer_id")
    if cid:
        for slot, val in facts.items():
            if val is None:  # Hủy kích hoạt rõ ràng (ví dụ: đã giải tỏa được lý do do dự/blocker)
                with db() as c:
                    c.execute(
                        "UPDATE profile SET active=0 WHERE customer_id=? AND slot=? AND active=1",
                        (cid, slot),
                    )
            else:
                upsert_slot(cid, slot, val, state.get("call_id", ""))
    outcome = state.get("call_outcome")
    if any(t["tool"] == "order_create" for t in state.get("tool_results", [])):
        outcome = "chot_don"
    return {
        "final_response": final,
        "call_outcome": outcome,
        "messages": [{"role": "assistant", "content": final or ""}],
    }
