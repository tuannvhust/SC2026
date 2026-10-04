"""
src/retrieval/query_router.py
Classify customer turns and route them to the appropriate handler:
- Product, specification, price, and comparison questions -> catalog RAG/tools.
- Order, delivery, and policy questions -> policy RAG/order tools.
- Objections (price concerns, hesitation, or asking others) -> objection handling.
- Small talk, greetings, and refusals -> conversational flow.
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
        """Analyze a customer turn and select the tool or module to call."""
        text_lower = turn_text.lower()

        # Apply basic rule-based routing, with optional LLM support.
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
