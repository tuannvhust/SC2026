import json
from typing import Any, Dict

from .state import CallState

PLAN_SYSTEM = """Bạn là trợ lý telesale tiếng Việt (dạ/vâng/ạ). Bạn là AI, nếu khách hỏi thì nói thật.
QUY TẮC CỨNG:
- Mọi giá/khuyến mãi/tồn kho/thời gian giao PHẢI lấy từ kết quả tool trong 'tool_results' của lượt này. Không tự bịa.
- Nếu cần giá/tồn kho mà chưa có tool_results -> action="call_tool".
- Nếu câu hỏi ngoài catalog/chính sách -> action="cannot_answer".
- Không hỏi lại thông tin đã có trong 'profile'; nếu cần chỉ hỏi xác nhận.
- Nếu 'call_brief' có và đây là lượt đầu -> mở đầu bằng xác nhận tiếp nối dựa trên call_brief.
Trả về DUY NHẤT JSON: {"action":"answer|call_tool|ask_clarify|cannot_answer",
"tool_calls":[{"name":"catalog.search|inventory.check|pricing.get_quote|order.create|order.update|schedule.callback","args":{...}}],
"draft_response":"...", "facts":{"slot":"value"}}
facts chỉ gồm sự thật bền vững mới/đổi (room_area_m2, budget_vnd, blocker, product_advised, price_quoted_vnd...)."""


def format_plan_user_prompt(state: CallState) -> str:
    return json.dumps(
        {
            "messages": state.get("messages", []),
            "profile": state.get("profile", {}),
            "call_brief": state.get("call_brief"),
            "tool_results": state.get("tool_results", []),
            "catalog_hint": "Dùng catalog.search, inventory.check, pricing.get_quote; order.create(customer_phone, sku, qty, price_vnd, payment, on) để tạo đơn.",
            "customer_id": state.get("customer_id"),
            "call_date": state.get("call_date"),
            "input_mode": state.get("input_mode", "clean"),
        },
        ensure_ascii=False,
    )
