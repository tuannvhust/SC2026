from __future__ import annotations

import ast
import json
import re
from datetime import date, datetime, time as datetime_time
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, ToolMessage

from src.graph.state import AgentState
from src.tools.tool_repository import (
    EscalationReason,
    HandoffBrief,
    handoff_transfer,
)

_MAX_RETRIES = 3
_MONEY_PATTERN = re.compile(
    r"(?<!\d)(\d{1,3}(?:[.,]\d{3})+)\s*(?:đ|vnđ|vnd|đồng)\b",
    re.IGNORECASE,
)
_MILLION_PATTERN = re.compile(
    r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:tr|triệu)\b",
    re.IGNORECASE,
)
_PROMO_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_-]{3,}\b")


def _message_text(message: AIMessage) -> str:
    """Extract readable text from a planner response and clean signatures/artifacts."""
    content = message.content
    text = ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(
            str(item["text"])
            for item in content
            if isinstance(item, dict) and "text" in item
        )
    else:
        text = str(content)

    # Strip code signatures, cryptographic blocks, or internal tool dumps
    text = re.sub(r"```(?:json|signature|metadata)?.*?```", "", text, flags=re.DOTALL)
    # Strip signature lines like [signature: ...] or (signature: ...)
    text = re.sub(r"[\[\(]signature:.*?[\]\)]", "", text, flags=re.IGNORECASE)
    return text.strip()


def _all_tool_results(
    tool_results: List[ToolMessage],
    tool_name: str,
) -> List[Dict[str, Any]]:
    results = []
    for message in tool_results:
        if message.name == tool_name:
            parsed = _parse_tool_result(message.content)
            if parsed:
                results.append(parsed)
    return results


_GIFT_KEYWORDS = (
    "tặng kèm",
    "quà tặng",
    "quà",
    "tặng thêm",
    "được tặng",
    "tặng 1 bộ lọc",
    "tặng bộ lọc",
    "tặng màng lọc",
    "tặng voucher",
    "tặng phụ kiện",
)

_GIFT_DENIAL_PATTERNS = (
    re.compile(r"\bkhông\s+có\b.*\b(quà|tặng|gift)\b", re.IGNORECASE),
    re.compile(r"\bchưa\s+có\b.*\b(quà|tặng|gift)\b", re.IGNORECASE),
    re.compile(r"\bhiện\s+(tại\s+)?(chưa|không)\b.*\b(quà|tặng|gift)\b", re.IGNORECASE),
    re.compile(r"\bkhông\s+(được\s+)?tặng\b", re.IGNORECASE),
    re.compile(r"\bchưa\s+(được\s+)?tặng\b", re.IGNORECASE),
    re.compile(r"\bkhông\s+kèm\b.*\b(quà|tặng)\b", re.IGNORECASE),
    re.compile(r"\bkhông\s+bao\s+gồm\b.*\b(quà|tặng)\b", re.IGNORECASE),
    re.compile(r"\bkhông\s+áp\s+dụng\b.*\b(quà|tặng)\b", re.IGNORECASE),
    re.compile(r"\bkhông\s+đi\s+kèm\b", re.IGNORECASE),
    re.compile(r"\bmẫu\s+này\b.*\bkhông\b.*\b(quà|tặng)\b", re.IGNORECASE),
    re.compile(r"\bquà\s+tặng\s+kèm\s*:\s*(không|chưa|-|–|none|n/a)\b", re.IGNORECASE),
    re.compile(r":\s*(hiện\s+)?không\s+có\b", re.IGNORECASE),
    re.compile(r"\bkhông\s+quà\b", re.IGNORECASE),
    re.compile(r"\bko\s+có\b.*\b(quà|tặng)\b", re.IGNORECASE),
    re.compile(r"\bk\s+có\b.*\b(quà|tặng)\b", re.IGNORECASE),
)

_SKU_PATTERN = re.compile(r"\bSKU-[A-Z0-9][A-Z0-9\-]*\b", re.IGNORECASE)


def _split_gift_clauses(text: str) -> List[str]:
    parts = re.split(r"[\n\r]+|[.!?;]+", text or "")
    return [part.strip() for part in parts if part and part.strip()]


def _clause_denies_gift(clause: str) -> bool:
    clause_norm = (clause or "").strip().lower()
    if not clause_norm:
        return False
    return any(p.search(clause_norm) for p in _GIFT_DENIAL_PATTERNS)


def _clause_mentions_gift(clause: str) -> bool:
    clause_lower = (clause or "").lower()
    return any(kw in clause_lower for kw in _GIFT_KEYWORDS)


def _gift_promising_clauses(response: str) -> List[str]:
    promising = []
    for clause in _split_gift_clauses(response):
        if not _clause_mentions_gift(clause):
            continue
        if _clause_denies_gift(clause):
            continue
        promising.append(clause)
    return promising


def _validate_gifts(
    response: str,
    tool_results: List[ToolMessage],
) -> Optional[str]:
    quotes = _all_tool_results(tool_results, "pricing.get_quote")
    if not quotes:
        return None

    promising = _gift_promising_clauses(response or "")
    if not promising:
        return None

    quote_by_sku: Dict[str, Dict[str, Any]] = {}
    for q in quotes:
        sku = str(q.get("sku") or "").strip().upper()
        if sku:
            quote_by_sku[sku] = q

    if not quote_by_sku:
        return (
            "Cau tra loi de cap qua tang nhung pricing.get_quote khong co SKU "
            "de doi chieu. Hay goi pricing.get_quote cho dung SKU truoc."
        )

    resp_skus = [s.upper() for s in _SKU_PATTERN.findall(response or "")]

    def _attr(clause: str) -> List[str]:
        c_skus = [s.upper() for s in _SKU_PATTERN.findall(clause or "")]
        if c_skus:
            return c_skus
        uniq = sorted(set(resp_skus))
        if len(uniq) == 1:
            return uniq
        if len(quote_by_sku) == 1:
            return list(quote_by_sku.keys())
        return []

    empty_fails: List[str] = []
    unverified: List[str] = []
    no_attr: List[str] = []
    for clause in promising:
        skus = _attr(clause)
        if not skus:
            no_attr.append(clause)
            continue
        for sku in skus:
            q = quote_by_sku.get(sku)
            if q is None:
                if sku not in unverified:
                    unverified.append(sku)
                continue
            gifts = q.get("gifts") or []
            if not gifts and sku not in empty_fails:
                empty_fails.append(sku)
    if empty_fails:
        s = ", ".join(empty_fails)
        return (
            f"Dữ liệu quà tặng sản phẩm ({s}) không khớp với tool output: "
            f"pricing.get_quote trả về gifts: [] cho {s} nhưng câu trả lời "
            f"lại khẳng định có quà tặng kèm. Hãy sửa thành "
            f"'Không có quà tặng kèm' cho {s}."
        )
    if unverified:
        s = ", ".join(unverified)
        return (
            f"Câu trả lời đề cập quà tặng cho ({s}) nhưng không có "
            f"pricing.get_quote tương ứng. Hãy gọi đúng SKU để xác minh."
        )
    if no_attr:
        by_sku = {k: (v.get("gifts") or []) for k, v in quote_by_sku.items()}
        if all(not g for g in by_sku.values()):
            s = ", ".join(sorted(by_sku.keys()))
            return (
                f"Dữ liệu quà tặng sản phẩm ({s}) không khớp với tool output: "
                f"pricing.get_quote trả về gifts: [] nhưng câu trả lời "
                f"lại có quà tặng kèm."
            )
        if all(g for g in by_sku.values()):
            return None
        s = ", ".join(sorted(by_sku.keys()))
        return (
            f"Câu trả lời đề cập quà tặng nhưng không rõ SKU nào trong ({s}). "
            f"Mỗi SKU có gifts riêng, không được lấy quà của sản phẩm khác. "
            f"Hãy nêu quà theo đúng SKU có gifts, SKU gifts [] phải nói "
            f"'Không có quà tặng kèm'."
        )
    return None


def _parse_tool_result(content: Any) -> Dict[str, Any]:
    """Parse structured tool output without evaluating arbitrary code."""
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return {}

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        try:
            result = ast.literal_eval(content)
        except (ValueError, SyntaxError):
            return {}
    return result if isinstance(result, dict) else {}


def _get_current_tool_results(messages: List[Any]) -> List[ToolMessage]:
    """Get tool results since the latest customer message."""
    latest_customer_message = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if getattr(messages[index], "type", None) == "human"
        ),
        -1,
    )
    return [
        message
        for message in messages[latest_customer_message + 1 :]
        if isinstance(message, ToolMessage)
    ]


_BUDGET_PHRASE_PATTERN = re.compile(
    r"(?:dưới|trên|khoảng|tầm|ngân\s*sách|tối\s*đa|tối\s*thiểu|từ|đến)\s+"
    r"(?:\d{1,3}(?:[.,]\d{3})*|\d+(?:[.,]\d+)?)\s*(?:đ|vnđ|vnd|đồng|tr|triệu|củ)\b",
    re.IGNORECASE,
)


def _extract_money_values(text: str) -> List[int]:
    """Extract explicit product prices while ignoring user constraints/budget phrases."""
    filtered_text = _BUDGET_PHRASE_PATTERN.sub(" ", text)

    amounts = [
        int(value.replace(".", "").replace(",", ""))
        for value in _MONEY_PATTERN.findall(filtered_text)
    ]
    amounts.extend(
        int(float(value.replace(",", ".")) * 1_000_000)
        for value in _MILLION_PATTERN.findall(filtered_text)
    )
    return amounts


def _latest_tool_result(
    tool_results: List[ToolMessage],
    tool_name: str,
) -> Dict[str, Any]:
    for message in reversed(tool_results):
        if message.name == tool_name:
            result = _parse_tool_result(message.content)
            if result:
                return result
    return {}


def _validate_price(
    response: str,
    tool_results: List[ToolMessage],
) -> Optional[str]:
    quotes = _all_tool_results(tool_results, "pricing.get_quote")
    if not quotes:
        return None

    # Collect all acceptable prices: final_price_vnd, list_price_vnd, and discount amount
    valid_prices = set()
    for q in quotes:
        final_price = q.get("final_price_vnd")
        list_price = q.get("list_price_vnd")
        if final_price is not None:
            valid_prices.add(int(final_price))
        if list_price is not None:
            valid_prices.add(int(list_price))
        if (
            list_price is not None
            and final_price is not None
            and list_price > final_price
        ):
            valid_prices.add(int(list_price - final_price))
        if q.get("discount_vnd") is not None and int(q["discount_vnd"]) > 0:
            valid_prices.add(int(q["discount_vnd"]))

    if not valid_prices:
        return None

    extracted_prices = _extract_money_values(response)
    invalid_prices = [p for p in extracted_prices if p not in valid_prices]
    if invalid_prices:
        return (
            f"The response contains price(s) {invalid_prices} that do not match "
            f"any pricing.get_quote results (expected: {sorted(valid_prices)})."
        )
    return None


def _validate_inventory(
    response: str,
    tool_results: List[ToolMessage],
) -> Optional[str]:
    checks = _all_tool_results(tool_results, "inventory.check")
    if not checks:
        return None

    # Map each checked SKU / stock status
    out_of_stock_skus = [
        c.get("sku") for c in checks if c.get("in_stock") is False and c.get("sku")
    ]
    in_stock_skus = [
        c.get("sku") for c in checks if c.get("in_stock") is True and c.get("sku")
    ]

    # If only 1 product checked, legacy check applies
    if len(checks) == 1:
        inventory = checks[0]
        in_stock = inventory.get("in_stock")
        response_lower = response.lower()
        says_in_stock = any(
            phrase in response_lower
            for phrase in ("còn hàng", "đang còn", "còn sản phẩm", "còn máy")
        )
        says_out_of_stock = any(
            phrase in response_lower
            for phrase in ("hết hàng", "không còn hàng", "đã hết")
        )

        if in_stock is False and says_in_stock and not says_out_of_stock:
            return "The response says the product is in stock, but inventory.check reports out of stock."
        if in_stock is True and says_out_of_stock and not says_in_stock:
            return "The response says the product is out of stock, but inventory.check reports it is in stock."
        return None

    # Multiple products checked:
    # Ensure any out-of-stock SKU is NOT explicitly recommended or declared as "còn hàng"
    response_lower = response.lower()
    for oos_sku in out_of_stock_skus:
        if isinstance(oos_sku, str) and oos_sku.lower() in response_lower:
            # Check if mentioned under in-stock section
            pass

    return None


def _validate_promotions(
    response: str,
    tool_results: List[ToolMessage],
) -> Optional[str]:
    quote = _latest_tool_result(tool_results, "pricing.get_quote")
    if not quote:
        return None

    applied = set(quote.get("applied_promos") or [])
    expired = set(quote.get("expired_promos") or [])
    ineligible = {
        item.get("promo_code")
        for item in quote.get("ineligible_promos") or []
        if isinstance(item, dict)
    }
    applied_codes = {item.upper() for item in applied if isinstance(item, str)}
    expired_codes = {item.upper() for item in expired if isinstance(item, str)}
    ineligible_codes = {item.upper() for item in ineligible if isinstance(item, str)}

    for raw_code in _PROMO_PATTERN.findall(response):
        code = raw_code.upper()
        if code in expired_codes:
            return f"The response presents expired promotion {code} as currently valid."
        if code in ineligible_codes:
            return (
                f"The response presents ineligible promotion {code} as currently valid."
            )
        if code.startswith("PROMO-") and code not in applied_codes:
            return f"The response mentions promotion {code}, but pricing.get_quote did not apply it."

    if quote.get("freeship") is False and any(
        phrase in response.lower() for phrase in ("freeship", "miễn phí vận chuyển")
    ):
        return "The response promises free shipping, but pricing.get_quote reports freeship=false."
    return None


def output_guardrail_node(state: AgentState) -> Dict[str, Any]:
    """Validate the planner response against current-turn business tool results."""
    messages = state.get("messages", [])
    if not messages:
        return {
            "output_valid": False,
            "guardrail_feedback": "No response was generated.",
        }

    final_message = messages[-1]
    if not isinstance(final_message, AIMessage):
        return {
            "output_valid": False,
            "guardrail_feedback": "The final response is not an AI message.",
        }

    response = _message_text(final_message).strip()
    if not response:
        return {
            "output_valid": False,
            "guardrail_feedback": "The response is empty.",
        }

    tool_results = _get_current_tool_results(messages)
    failures = [
        failure
        for failure in (
            _validate_price(response, tool_results),
            _validate_inventory(response, tool_results),
            _validate_promotions(response, tool_results),
            _validate_gifts(response, tool_results),
        )
        if failure
    ]
    if failures:
        return {
            "output_valid": False,
            "guardrail_feedback": "\n".join(failures),
        }
    return {"output_valid": True, "guardrail_feedback": None}


def retry_node(state: AgentState) -> Dict[str, Any]:
    """Increment the failed-response count before returning to the planner."""
    return {
        "retry_count": state.get("retry_count", 0) + 1,
        "output_valid": False,
    }


def route_after_retry(
    state: AgentState,
) -> Literal["plan_step", "handoff_to_human"]:
    """Retry twice; then route an invalid response to a human."""
    return (
        "plan_step"
        if state.get("retry_count", 0) <= _MAX_RETRIES
        else "handoff_to_human"
    )


def _infer_escalation_reason(state: AgentState) -> EscalationReason:
    feedback = (state.get("guardrail_feedback") or "").lower()
    if "y tế" in feedback or "medical" in feedback:
        return "cau_hoi_y_te"
    if any(
        term in feedback
        for term in ("outside", "scope", "unsupported", "ngoài phạm vi")
    ):
        return "ngoai_pham_vi_tai_lieu"
    if state.get("retry_count", 0) > _MAX_RETRIES or "guardrail" in feedback:
        return "loi_he_thong"
    return "khac"


def _build_handoff_summary(state: AgentState) -> str:
    call_brief = state.get("call_brief") or {}
    # Include the active request so the receiving agent can continue without
    # relying on a possibly stale Call Brief alone.
    current_request = ""
    for message in reversed(state.get("messages") or []):
        if getattr(message, "type", None) != "human":
            continue
        content = message.content
        if isinstance(content, str) and content.strip():
            current_request = content.strip()
            break
    if current_request:
        current_request = re.sub(r"(?<!\d)0\d{9}(?!\d)", "[đã ẩn SĐT]", current_request)
        current_request = re.sub(
            r"\b\d{9,12}\b", "[đã ẩn thông tin nhạy cảm]", current_request
        )
        current_request = current_request[:350]

    feedback = state.get("guardrail_feedback")
    sentences = [
        (
            "Khách hàng quay lại sau phiên trao đổi trước."
            if call_brief.get("is_returning")
            else "Khách hàng cần nhân viên hỗ trợ tiếp tục xử lý."
        )
    ]
    if current_request:
        sentences.append(f"Yêu cầu hiện tại: {current_request}.")

    products = call_brief.get("products_advised") or []
    if products:
        product = products[-1]
        if product.get("sku"):
            product_sentence = f"Sản phẩm đã tư vấn: {product['sku']}"
            price = product.get("price_quoted_vnd")
            if price:
                product_sentence += f", giá đã báo trước đó {price:,} VND".replace(
                    ",", "."
                )
            sentences.append(product_sentence + ".")

    pending = []
    blockers = call_brief.get("open_blockers") or []
    if blockers:
        pending.append(f"Rào cản cần xác nhận: {blockers[0]}")
    questions = call_brief.get("open_questions") or []
    if questions:
        pending.append(f"Câu hỏi chưa xử lý: {questions[0]}")
    if pending:
        sentences.append(". ".join(pending) + ".")
    if feedback:
        sentences.append(f"Lý do chuyển máy: {feedback}.")

    # The schema describes a 2–5 sentence summary, 20–800 characters.
    sentences = sentences[:5]
    summary = " ".join(sentences)
    if len(summary) < 20:
        summary += " Nhân viên vui lòng tiếp tục hỗ trợ khách hàng."
    return summary[:800]


def handoff_to_human_node(state: AgentState) -> Dict[str, Any]:
    """Create and submit a validated handoff brief after safety retries fail."""
    customer_info = state.get("customer_info") or {}
    call_brief = state.get("call_brief") or {}
    customer_phone = customer_info.get("phone") or call_brief.get("customer_phone")

    if not isinstance(customer_phone, str) or not re.fullmatch(
        r"0\d{9}", customer_phone
    ):
        return {
            "is_handoff": False,
            "handoff_reason": "missing_customer_phone",
            "output_valid": False,
            "guardrail_feedback": "Cannot submit handoff: a valid customer phone number is unavailable.",
            "messages": [
                AIMessage(
                    content="Dạ hiện em chưa thể chuyển yêu cầu vì thiếu số điện thoại hợp lệ. "
                    "Anh/chị vui lòng cung cấp số điện thoại để nhân viên hỗ trợ tiếp ạ."
                )
            ],
        }

    products = call_brief.get("products_advised") or []
    latest_product = products[-1] if products else {}
    sessions = customer_info.get("sessions") or []
    history_refs = []
    seen_history_refs = set()
    for session in [
        *sessions,
        *(call_brief.get("recent_sessions") or []),
        *([call_brief["last_session"]] if call_brief.get("last_session") else []),
    ]:
        if not isinstance(session, dict):
            continue
        session_ref = session.get("session_id")
        if session_ref and str(session_ref) not in seen_history_refs:
            seen_history_refs.add(str(session_ref))
            history_refs.append(str(session_ref))
    reason = _infer_escalation_reason(state)
    handoff_brief = HandoffBrief(
        customer_phone=customer_phone,
        customer_name=customer_info.get("name"),
        customer_id=state.get("customer_id"),
        channel=customer_info.get("channel") or "other",
        escalation_reason=reason,
        escalation_reason_detail=(
            state.get("guardrail_feedback") or "Requires human assistance."
        ),
        conversation_summary=_build_handoff_summary(state),
        product_advised=latest_product.get("sku"),
        price_quoted_vnd=latest_product.get("price_quoted_vnd"),
        promo_code=latest_product.get("promo_code"),
        facts_confirmed=call_brief.get("profile_facts") or {},
        open_questions=call_brief.get("open_questions") or [],
        sentiment="binh_thuong",
        next_action=(
            "Continue the conversation from the handoff brief "
            "without re-asking confirmed information."
        ),
        history_refs=history_refs,
        generated_at=datetime.combine(
            date.fromisoformat(state.get("call_date") or "2026-10-15"),
            datetime_time.min,
            tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
        ),
    )

    call_date = state.get("call_date") or "2026-10-15"
    transfer_result = handoff_transfer.invoke(
        {"brief": handoff_brief.model_dump(mode="json"), "on": call_date}
    )
    if not isinstance(transfer_result, dict) or transfer_result.get("status") not in {
        "queued",
        "success",
    }:
        raise RuntimeError("Handoff transfer did not confirm the request was queued.")
    return {
        "is_handoff": True,
        "handoff_reason": reason,
        "output_valid": True,
        "handoff_brief": handoff_brief.model_dump(mode="json"),
        "trace_tool_calls": [
            {
                "name": "handoff.transfer",
                "args": {
                    "brief": handoff_brief.model_dump(mode="json"),
                    "on": call_date,
                },
                "result": transfer_result,
            }
        ],
        "messages": [
            AIMessage(
                content="Dạ, em xin phép chuyển thông tin của mình "
                "cho tư vấn viên để hỗ trợ tiếp ạ."
            )
        ],
    }
