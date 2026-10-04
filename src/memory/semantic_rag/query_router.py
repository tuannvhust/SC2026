'''src/memory/semantic_rag/query_router.py
Query router for raw user queries.
Provides intent classification and metadata extraction for product/policy searches.
'''

import re
from typing import Dict, Any, Optional

# Simple regex patterns for Vietnamese-language intents.
INTENT_PATTERNS = {
    "product": re.compile(
        r"\b(mua|tìm|sản phẩm|sku|giá|trong kho|dòng|máy|hãng|bán|có sẵn|mẫu|iphone|samsung|oppo|xiaomi)\b",
        re.IGNORECASE
    ),
    "policy": re.compile(r"\b(đổi trả|bảo hành|giao hàng|chính sách)\b", re.IGNORECASE),
    "order_closing": re.compile(r"\b(thanh toán|đặt hàng|đơn hàng|hủy|hoàn tiền)\b", re.IGNORECASE),
    "complaint": re.compile(r"\b(khó|phàn nàn|góp ý|đánh giá|sự cố)\b", re.IGNORECASE),
    "smalltalk": re.compile(r"^\s*(chào|xin chào|cám ơn|cảm ơn|hello|hi)\s*$", re.IGNORECASE),
}

def _detect_intent(query: str) -> str:
    """Return intent key based on matching patterns. Defaults to 'smalltalk'."""
    for intent, pat in INTENT_PATTERNS.items():
        if pat.search(query):
            return intent
    return "smalltalk"

def _extract_price_range(query: str) -> Dict[str, Optional[int]]:
    """Extract simple price range expressions like 'giá dưới 10 triệu' or 'giá từ 5 tới 8 triệu'."""
    min_price, max_price = None, None
    # Under X million
    m = re.search(r"gi[áà] (?:dưới|<)\s*(\d+(?:[.,]\d+)?)\s*triệu", query, re.IGNORECASE)
    if m:
        max_price = int(float(m.group(1).replace(',', '.')) * 1_000_000)
    # Between X and Y million
    m = re.search(r"gi[áà] (?:từ|from)\s*(\d+(?:[.,]\d+)?)\s*(?:đến|to)\s*(\d+(?:[.,]\d+)?)\s*triệu", query, re.IGNORECASE)
    if m:
        min_price = int(float(m.group(1).replace(',', '.')) * 1_000_000)
        max_price = int(float(m.group(2).replace(',', '.')) * 1_000_000)
    return {"min_price": min_price, "max_price": max_price}

def _extract_stock_filter(query: str) -> bool:
    """Return True if user explicitly wants items in stock ("trong kho")."""
    return bool(re.search(r"trong\s*kho", query, re.IGNORECASE))

def _extract_category(query: str) -> Optional[str]:
    # Values must match the normalized category stored in Qdrant payloads.
    categories = {
        "điện thoại": "dien_thoai",
        "tivi": "tivi",
        "máy tính": "laptop",
        "laptop": "laptop",
        "tablet": "tablet",
        "tai nghe": "tai_nghe",
    }
    query_lower = query.lower()
    for label, payload_value in categories.items():
        if label in query_lower:
            return payload_value
    return None

def route(raw_query: str) -> Dict[str, Any]:
    """Route a raw user query.

    Returns a dictionary with keys:
        intent: one of ['product', 'policy', 'order_closing', 'complaint', 'smalltalk']
        collection: 'products' | 'policies' | None
        metadata: dict with possible filters (category, in_stock_only, min_price, max_price)
        early_response: str | None – canned answer for smalltalk/intents that do not need retrieval.
    """
    intent = _detect_intent(raw_query)
    result = {
        "intent": intent,
        "collection": None,
        "metadata": {},
        "early_response": None,
    }

    if intent == "smalltalk":
        result["early_response"] = "Chào anh/chị! Em có thể giúp gì cho bạn hôm nay?"
        return result

    if intent == "product":
        result["collection"] = "products"
        result["metadata"]["category"] = _extract_category(raw_query)
        result["metadata"]["in_stock_only"] = _extract_stock_filter(raw_query)
        result["metadata"].update(_extract_price_range(raw_query))
        return result

    if intent == "policy":
        result["collection"] = "policies"
        return result

    if intent in ("order_closing", "complaint"):
        result["early_response"] = "Cảm ơn bạn đã liên hệ. Chúng tôi sẽ hỗ trợ nhanh nhất có thể."
        return result

    # Fallback – treat as smalltalk
    result["early_response"] = "Chào anh/chị! Em có thể giúp gì cho bạn hôm nay?"
    return result
