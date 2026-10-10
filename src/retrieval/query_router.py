"""
src/retrieval/query_router.py
Phân loại lượt thoại của khách hàng để định tuyến xử lý phù hợp:
- hỏi sản phẩm / cấu hình / giá / so sánh -> RAG catalog / tools/catalog
- hỏi đơn hàng / vận chuyển / chính sách -> RAG policies / tools/order
- phản đối (giá cao, phân vân, hỏi người thân) -> objection handling strategy
- chitchat / chào hỏi / từ chối -> conversational flow
"""

from typing import Dict, Any
from enum import Enum


class TurnType(str, Enum):
    PRODUCT_QUERY = "product_query"
    POLICY_QUERY = "policy_query"
    ORDER_QUERY = "order_query"
    OBJECTION = "objection"
    CHITCHAT = "chitchat"
    ORDER_INTENT = "order_intent"


class QueryRouter:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def route(self, turn_text: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Phân tích lượt thoại và quyết định tool/module cần gọi.
        """
        text_lower = turn_text.lower()

        # Quy tắc định tuyến cơ bản (Rule-based kết hợp LLM)
        if any(w in text_lower for w in ["đổi trả", "bảo hành", "ship", "giao hàng", "phí vận chuyển", "cod"]):
            return {
                "turn_type": TurnType.POLICY_QUERY,
                "recommended_tool": "retrieval.search_policies",
                "target": "policies"
            }

        if any(w in text_lower for w in ["giá", "cấu hình", "bao nhiêu tiền", "ram", "pin", "màu", "so sánh", "có máy nào"]):
            return {
                "turn_type": TurnType.PRODUCT_QUERY,
                "recommended_tool": "retrieval.search_products",
                "target": "catalog"
            }

        if any(w in text_lower for w in ["đắt quá", "giá cao", "để hỏi", "suy nghĩ thêm", "chưa mua"]):
            return {
                "turn_type": TurnType.OBJECTION,
                "recommended_tool": "harness.handle_objection",
                "target": "objection_bank"
            }

        if any(w in text_lower for w in ["chốt", "đặt hàng", "mua máy này", "lấy con này"]):
            return {
                "turn_type": TurnType.ORDER_INTENT,
                "recommended_tool": "tools.order_create",
                "target": "orders"
            }

        return {
            "turn_type": TurnType.CHITCHAT,
            "recommended_tool": "harness.chat_reply",
            "target": "direct_reply"
        }

