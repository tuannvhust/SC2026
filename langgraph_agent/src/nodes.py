import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime
from typing import Any, Dict

from .guardrails import guardrail_check
from .llm import fake_plan, real_llm_json, real_llm_text, use_fake_llm
from .memory import db, get_or_create_customer, load_episodic, load_profile, upsert_slot
from .prompts import PLAN_SYSTEM, format_plan_user_prompt
from .state import CallState
from .tools import CATALOG, DEFAULT_CATALOG_SEARCH, TOOLS, crm_get_customer, mask_pii

TOOL_TIMEOUT_S = 5
_executor = ThreadPoolExecutor(max_workers=4)


def input_guardrail(state: CallState) -> CallState:
    """Reject empty, oversized or prompt-injection-like input before any lookup."""
    text = (state.get("raw_customer_text") or "").strip()
    reason = None
    if not text:
        reason = "empty_input"
    elif len(text) > 2000:
        reason = "input_too_long"
    elif re.search(r"(ignore|bỏ qua).{0,30}(instruction|hướng dẫn|quy tắc)", text, re.I):
        reason = "prompt_injection"
    return {"input_valid": reason is None, "input_rejection_reason": reason}


def input_refusal(state: CallState) -> CallState:
    """Produce a safe response for input rejected by the input guardrail."""
    return {
        "final_response": "Dạ em chưa thể xử lý yêu cầu này. Anh/chị vui lòng gửi lại nội dung cần hỗ trợ ngắn gọn hơn ạ.",
        "call_outcome": "tu_choi_dau_vao",
    }


def resolve_identity(state: CallState) -> CallState:
    """Resolve phone/channel identity; ambiguous phones must not load facts."""
    started = time.perf_counter()
    data = crm_get_customer(phone=state.get("customer_phone"),
                            zalo_id=state.get("channel_identity") if state.get("channel") == "zalo_oa" else None,
                            fb_id=state.get("channel_identity") if state.get("channel") == "chat_fanpage" else None)
    if data.get("ambiguous"):
        return {"crm_result": data, "needs_identity_confirm": True,
                "candidates": data.get("candidates", []), "call_brief": None,
                "call_brief_latency_ms": int((time.perf_counter() - started) * 1000)}
    is_returning = bool(data.get("found") and not data.get("ambiguous"))
    if not data.get("found") and state.get("customer_phone"):
        cid, returning = get_or_create_customer(state["customer_phone"])
        data.update({"found": True, "customer_id": cid, "name": None, "honorific": None,
                     "orders": [], "sessions": [], "ambiguous": False})
        is_returning = returning
    cid = data.get("customer_id")
    profile = {} if state.get("config") == "baseline_no_memory" else load_profile(cid) if cid else {}
    return {"crm_result": data, "customer_id": cid, "customer_name": data.get("name"),
            "honorific": data.get("honorific"), "is_returning_customer": is_returning,
            "profile": profile, "episodic_summaries": (data.get("sessions", []) + load_episodic(cid)) if cid and state.get("config") != "baseline_no_memory" else data.get("sessions", []),
            "orders": data.get("orders", []), "call_id": state.get("call_id", ""),
            "call_brief_latency_ms": int((time.perf_counter() - started) * 1000)}


def build_call_brief(state: CallState) -> CallState:
    """Build the schema-compatible brief; stale prices are never reused as quotes."""
    has_assistant_turn = any(m["role"] == "assistant" for m in state.get("messages", []))
    if state.get("needs_identity_confirm") or not state.get("is_returning_customer") or has_assistant_turn:
        return {"call_brief": None}
    profile, episodic = state.get("profile", {}), state.get("episodic_summaries", [])
    if not profile and not episodic and not state.get("orders"):
        return {"call_brief": None}

    # LƯU Ý: Câu mở đầu chủ động KHÔNG chứa bất kỳ con số giá nào. Giá bán luôn được
    # tra cứu lại từ catalog tool và được plan_step phát ngôn, tránh rò rỉ giá cũ từ bộ nhớ.
    facts_for_brief = {"product": CATALOG.get(profile.get("product_advised", ""), {}).get("name"),
                       "blocker": profile.get("blocker"), "last_call": episodic[0] if episodic else None}
    if use_fake_llm():
        parts = ["Dạ em chào anh/chị,"]
        if facts_for_brief["product"]:
            parts.append(f"hôm trước bên em có tư vấn {facts_for_brief['product']}.")
        if facts_for_brief["blocker"]:
            parts.append("Anh/chị đã trao đổi với người nhà chưa ạ, hay còn băn khoăn điểm nào để em hỗ trợ thêm?")
        opening = " ".join(parts)
    # ĐÁNH GIÁ: Có thể tinh chỉnh câu prompt tiếng Việt theo phong cách bán hàng mong muốn
    else:
        opening = real_llm_text(
            "Viết 1-2 câu mở đầu tiếng Việt (dạ/ạ) xác nhận tiếp nối cuộc gọi trước. KHÔNG nêu con số giá. "
            "KHÔNG hỏi lại thông tin đã biết. Chỉ dùng dữ kiện được cung cấp.",
            json.dumps(facts_for_brief, ensure_ascii=False),
        )
    brief = {"customer_phone": state.get("customer_phone"), "customer_name": state.get("customer_name"),
             "honorific": state.get("honorific"), "is_returning": True,
             "n_previous_sessions": len(episodic), "last_session": episodic[0] if episodic else None,
             "profile_facts": profile, "products_advised": [{"sku": profile.get("product_advised"),
             "price_quoted_vnd": profile.get("price_quoted_vnd"), "quoted_on": state.get("call_date")}]
             if profile.get("product_advised") else [], "orders": state.get("orders", []),
             "open_blockers": [profile["blocker"]] if profile.get("blocker") else [],
             "open_questions": [], "must_not_ask": list(profile), "stale_warnings": [],
             "suggested_opening": opening, "suggested_next_action": "xác nhận nhu cầu hiện tại",
             "generated_at": datetime.utcnow().isoformat() + "Z", "latency_ms": state.get("call_brief_latency_ms", 0),
             "precomputed_parts": ["profile", "sessions"]}
    return {"call_brief": brief}


def input_normalize(state: CallState) -> CallState:
    """Normalize deterministic ASR/teencode inputs while retaining raw customer text."""
    if not state.get("messages"): return {}
    raw = state["messages"][-1]["content"]
    text = raw
    if state.get("input_mode") == "asr_transcript":
        text = re.sub(r"bốn pờ rô", "4 Pro", text, flags=re.I)
        text = re.sub(r"ba mươi lăm", "35", text, flags=re.I)
        text = re.sub(r"năm triệu rưỡi", "5,5 triệu", text, flags=re.I)
        text = re.sub(r"mét vuông", "m2", text, flags=re.I)
    elif state.get("input_mode") == "chat_teencode":
        text = re.sub(r"\be\s+oi\b", "em ơi", text, flags=re.I)
        text = re.sub(r"\bok\s+r\b", "đồng ý rồi", text, flags=re.I)
        text = re.sub(r"\bsp\b", "sản phẩm", text, flags=re.I)
    if text != raw:
        state["messages"][-1] = {"role": "user", "content": text}
    return {"normalized_customer_text": text}


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
    if action not in {"answer", "call_tool", "ask_clarify", "cannot_answer", "rag"}:
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
    results = list(state.get("pending_tool_results", []))
    for tc in state.get("tool_calls", []):
        name = tc.get("name")
        # Keep the legacy alias patchable for timeout/fault-injection tests.
        alias = TOOLS.get("catalog_search")
        fn = alias if name == "catalog.search" and alias is not DEFAULT_CATALOG_SEARCH else TOOLS.get(name)
        if fn is None:
            return {"needs_handoff": True, "handoff_reason": "tool_error"}
        args = dict(tc.get("args", {}))
        if name in {"inventory.check", "pricing.get_quote", "order.create", "order.update"}:
            args.setdefault("on", state.get("call_date", "2026-10-15"))
        try:
            fut = _executor.submit(fn, **args)
            res = fut.result(timeout=TOOL_TIMEOUT_S)
        except FutureTimeout:
            return {"needs_handoff": True, "handoff_reason": "tool_timeout"}
        except Exception:
            return {"needs_handoff": True, "handoff_reason": "tool_error"}
        if name == "pricing.get_quote" and isinstance(res, dict):
            res = {k: v for k, v in res.items() if k != "_internal_price_floor_vnd"}
        results.append({"tool": name, "name": name, "args": args, "result": res})
    return {
        "pending_tool_results": results,
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "tool_calls": [],
    }


def rag_tool(state: CallState) -> CallState:
    """Query policy KB through the same controlled tool execution boundary."""
    query = state.get("normalized_customer_text") or state.get("raw_customer_text", "")
    fn = TOOLS["policy_kb.search"]
    return {"pending_tool_results": [{"tool": "policy_kb.search", "name": "policy_kb.search",
                                       "args": {"query": query}, "result": fn(query=query)}]}


def collect_tool_results(state: CallState) -> CallState:
    """Commit tool/RAG results to the planner-visible state in one place."""
    return {"tool_results": list(state.get("tool_results", [])) + list(state.get("pending_tool_results", [])),
            "pending_tool_results": []}


def trace_emit(state: CallState) -> CallState:
    """Emit one evaluator-compatible JSONL record per agent turn."""
    text = state.get("final_response") or state.get("draft_response") or ""
    questions = []
    for q in re.findall(r"([^?？]{2,100}[?？])", text):
        slot = "general"
        for candidate in ("room_area_m2", "budget_vnd", "size", "address", "payment", "product_advised"):
            if candidate.replace("_", " ") in q.lower(): slot = candidate
        questions.append({"slot": slot, "type": "confirm" if any(x in q.lower() for x in ("đúng không", "vẫn", "phải không")) else "open", "text": q.strip()})
    claims = []
    for value in re.findall(r"\d{1,3}(?:\.\d{3})+", text):
        claims.append({"field": "price_vnd", "value": int(value.replace(".", "")), "text": value})
    writes = []
    for key, value in (state.get("facts_to_persist") or {}).items():
        writes.append({"key": key, "value": value, "op": "delete" if value is None else "set",
                       "source": f"{state.get('call')}#turn{state.get('turn', 1)}", "customer_id": state.get("customer_id")})
    row = {"run_id": state.get("run_id", "local"), "config": state.get("config", "full"),
           "scenario_id": state.get("scenario_id", "local"), "call": state.get("call", "call_1"),
           "turn": state.get("turn", 1), "customer_text": state.get("raw_customer_text", ""),
           "agent_text": text, "questions": questions, "claims": claims,
           "facts_used": state.get("facts_used", []), "tool_calls": state.get("tool_results", []),
           "memory_writes": writes, "latency": state.get("latency", {"ttft_ms": 0, "total_ms": 0}),
           "call_brief_latency_ms": state.get("call_brief_latency_ms"), "customer_input_mode": state.get("input_mode", "clean")}
    path = state.get("trace_path")
    if path:
        with open(path, "a", encoding="utf-8") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"questions": questions, "claims": claims, "memory_writes": writes, "pending_trace": row}


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
    reason_map = {"cannot_answer": "ngoai_pham_vi_tai_lieu", "tool_timeout": "loi_he_thong",
                  "tool_error": "loi_he_thong", "guardrail_exceeded": "loi_he_thong"}
    brief = {"customer_phone": state.get("customer_phone"), "customer_name": state.get("customer_name"),
             "customer_id": state.get("customer_id"), "channel": state.get("channel", "other"),
             "escalation_reason": reason_map.get(reason, "khac"), "escalation_reason_detail": last_user,
             "conversation_summary": f"Khách cần hỗ trợ: {last_user[:500]}",
             "product_advised": profile.get("product_advised"), "price_quoted_vnd": profile.get("price_quoted_vnd"),
             "open_questions": [last_user], "next_action": "nhân viên tiếp nhận và trả lời câu hỏi của khách",
             "generated_at": datetime.utcnow().isoformat() + "Z", "facts_confirmed": profile,
             "sentiment": "binh_thuong"}
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
        "call_outcome": "chuyen_may", "handoff_result": TOOLS["handoff.transfer"](brief=brief),
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
    if any(t.get("tool") == "order.create" or t.get("name") == "order.create" for t in state.get("tool_results", [])):
        outcome = "chot_don"
    return {
        "final_response": final,
        "call_outcome": outcome,
        "messages": [{"role": "assistant", "content": final or ""}],
    }


def persist_call(state: CallState) -> CallState:
    """Persist an episodic summary when the caller explicitly ends the call."""
    cid = state.get("customer_id")
    if not cid:
        return {}
    user_lines = [m["content"] for m in state.get("messages", []) if m.get("role") == "user"]
    summary = f"Khách nói: {' | '.join(user_lines)[:200]}. Kết quả: {state.get('call_outcome') or 'hen_lai'}."
    with db() as c:
        c.execute("INSERT INTO episodic(customer_id,call_id,ts,summary,outcome) VALUES (?,?,?,?,?)",
                  (cid, state.get("call_id"), datetime.now().isoformat(), summary,
                   state.get("call_outcome") or "hen_lai"))
    return {"call_summary": summary}
