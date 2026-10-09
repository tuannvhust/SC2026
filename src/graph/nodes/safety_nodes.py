from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import AIMessage, ToolMessage

from src.graph.state import AgentState
from src.tools.tool_repository import HandoffBrief, handoff_transfer

_MAX_RETRIES = 2
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
    """Extract readable text from a planner response."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(item["text"])
            for item in content
            if isinstance(item, dict) and "text" in item
        )
    return str(content)


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


def _extract_money_values(text: str) -> List[int]:
    """Extract explicit VND amounts and amounts expressed in millions."""
    amounts = [
        int(value.replace(".", "").replace(",", ""))
        for value in _MONEY_PATTERN.findall(text)
    ]
    amounts.extend(
        int(float(value.replace(",", ".")) * 1_000_000)
        for value in _MILLION_PATTERN.findall(text)
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
    quote = _latest_tool_result(tool_results, "pricing.get_quote")
    expected_price = quote.get("final_price_vnd")
    if expected_price is None:
        return None

    if any(price != expected_price for price in _extract_money_values(response)):
        return "The response contains a price that does not match pricing.get_quote."
    return None


def _validate_inventory(
    response: str,
    tool_results: List[ToolMessage],
) -> Optional[str]:
    inventory = _latest_tool_result(tool_results, "inventory.check")
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

    if in_stock is False and says_in_stock:
        return "The response says the product is in stock, but inventory.check reports out of stock."
    if in_stock is True and says_out_of_stock:
        return "The response says the product is out of stock, but inventory.check reports it is in stock."
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
            return f"The response presents ineligible promotion {code} as currently valid."
        if code.startswith("PROMO-") and code not in applied_codes:
            return f"The response mentions promotion {code}, but pricing.get_quote did not apply it."

    if quote.get("freeship") is False and any(
        phrase in response.lower()
        for phrase in ("freeship", "miễn phí vận chuyển")
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


def _infer_escalation_reason(state: AgentState) -> str:
    feedback = (state.get("guardrail_feedback") or "").lower()
    if "y tế" in feedback or "medical" in feedback:
        return "cau_hoi_y_te"
    if any(term in feedback for term in ("outside", "scope", "unsupported", "ngoài phạm vi")):
        return "ngoai_pham_vi_tai_lieu"
    if state.get("retry_count", 0) > _MAX_RETRIES or "guardrail" in feedback:
        return "loi_he_thong"
    return "khac"


def _build_handoff_summary(state: AgentState) -> str:
    call_brief = state.get("call_brief") or {}
    parts = []

    if call_brief.get("is_returning"):
        parts.append("Khách hàng quay lại sau các phiên trao đổi trước.")

    products = call_brief.get("products_advised") or []
    if products:
        product = products[-1]
        if product.get("sku"):
            parts.append(f"Sản phẩm đã tư vấn: {product['sku']}.")
        price = product.get("price_quoted_vnd")
        if price:
            parts.append(f"Giá đã báo trước đó: {price:,} VND.".replace(",", "."))

    blockers = call_brief.get("open_blockers") or []
    if blockers:
        parts.append(f"Rào cản hiện tại: {blockers[0]}.")

    questions = call_brief.get("open_questions") or []
    if questions:
        parts.append(f"Câu hỏi chưa xử lý: {questions[0]}.")

    feedback = state.get("guardrail_feedback")
    if feedback:
        parts.append(f"Lý do chuyển máy: {feedback}")

    summary = " ".join(parts) or "Cuộc hội thoại cần nhân viên hỗ trợ tiếp tục xử lý."
    if len(summary) < 20:
        summary = "Cuộc hội thoại cần được chuyển cho nhân viên để tiếp tục xử lý."
    return summary[:800]


def handoff_to_human_node(state: AgentState) -> Dict[str, Any]:
    """Create and submit a validated handoff brief after safety retries fail."""
    customer_info = state.get("customer_info") or {}
    call_brief = state.get("call_brief") or {}
    customer_phone = customer_info.get("phone") or call_brief.get("customer_phone")

    if not isinstance(customer_phone, str) or not re.fullmatch(r"0\d{9}", customer_phone):
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
    reason = _infer_escalation_reason(state)
    handoff_brief = HandoffBrief(
        customer_phone=customer_phone,
        customer_name=customer_info.get("name"),
        customer_id=state.get("customer_id"),
        channel=customer_info.get("channel"),
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
        history_refs=[
            str(session["session_id"])
            for session in sessions
            if session.get("session_id")
        ],
        generated_at=datetime.now().isoformat(),
    )

    transfer_result = handoff_transfer.invoke(
        {"brief": handoff_brief.model_dump(mode="json")}
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
        "messages": [
            AIMessage(
                content="Dạ, em xin phép chuyển thông tin của mình "
                "cho tư vấn viên để hỗ trợ tiếp ạ."
            )
        ],
    }
