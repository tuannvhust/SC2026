"""Gemini structured-output router for raw user queries."""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    model_validator,
)

logger = logging.getLogger(__name__)

Category = Literal[
    "gia-dung/combo",
    "gia-dung/may-loc-khong-khi",
    "gia-dung/may-loc-nuoc",
    "gia-dung/noi-chien",
    "gia-dung/phu-kien",
    "gia-dung/quat",
    "me-be",
    "thoi-trang/ao-khoac",
    "thoi-trang/giay",
    "thoi-trang/phu-kien",
]

CATEGORY_GUIDE = {
    "gia-dung/combo": "combo, bộ sản phẩm gia dụng",
    "gia-dung/may-loc-khong-khi": (
        "máy lọc không khí, máy lọc khí, lọc không khí, air purifier"
    ),
    "gia-dung/may-loc-nuoc": "máy lọc nước, lọc nước, máy RO",
    "gia-dung/noi-chien": "nồi chiên, nồi chiên không dầu, air fryer",
    "gia-dung/phu-kien": "phụ kiện gia dụng, màng lọc, lõi lọc",
    "gia-dung/quat": "quạt, quạt máy",
    "me-be": (
        "mẹ và bé, mẹ bé, máy hút sữa, máy hâm sữa, máy tiệt trùng, "
        "xe đẩy, bình sữa, túi trữ sữa, ghế ngồi ô tô cho trẻ"
    ),
    "thoi-trang/ao-khoac": "áo khoác, áo phao, áo jacket",
    "thoi-trang/giay": "giày, giày thể thao",
    "thoi-trang/phu-kien": "tất, vớ, phụ kiện thời trang",
}


class QueryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Optional[Category] = Field(
        description=(
            "Exact Qdrant product category from the allowed category enum, "
            "or null when no specific category is supported by the question."
        )
    )
    in_stock_only: StrictBool = Field(
        description="True only when the customer explicitly requires available stock."
    )
    min_price: Optional[StrictInt] = Field(
        ge=0,
        description=(
            "Spoken minimum price boundary in whole VND before applying "
            "min_price_exclusive, or null."
        ),
    )
    max_price: Optional[StrictInt] = Field(
        ge=0,
        description=(
            "Spoken maximum price boundary in whole VND before applying "
            "max_price_exclusive, or null."
        ),
    )
    room_area_m2: Optional[StrictInt | StrictFloat] = Field(
        ge=0,
        description=(
            "Requested room area in square meters, or null. Retrieval should only "
            "keep products whose supported room area is at least this value."
        ),
    )
    min_price_exclusive: StrictBool = Field(
        default=False,
        description="Internal bound marker: true only for a strict lower price bound.",
    )
    max_price_exclusive: StrictBool = Field(
        default=False,
        description="Internal bound marker: true only for a strict upper price bound.",
    )


class QueryRouteExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["product", "policy", "order_closing", "complaint", "smalltalk"]
    collection: Optional[Literal["products", "policies"]]
    metadata: QueryMetadata
    early_response: Optional[str] = Field(
        description=(
            "A concise Vietnamese response for smalltalk, complaints, or order "
            "closing intents; null when retrieval is needed."
        )
    )

    @model_validator(mode="after")
    def validate_intent_routing(self) -> "QueryRouteExtraction":
        expected_collection = {
            "product": "products",
            "policy": "policies",
        }.get(self.intent)
        if self.collection != expected_collection:
            raise ValueError(
                f"intent {self.intent!r} must use collection "
                f"{expected_collection!r}"
            )
        if expected_collection is None and not self.early_response:
            raise ValueError("Non-retrieval intents require early_response.")
        if expected_collection is not None and self.early_response is not None:
            raise ValueError("Retrieval intents must not return early_response.")
        if self.intent != "product" and self.metadata.category is not None:
            raise ValueError("Only product intent may specify a product category.")
        if self.intent != "product" and (
            self.metadata.in_stock_only
            or self.metadata.min_price is not None
            or self.metadata.max_price is not None
            or self.metadata.room_area_m2 is not None
        ):
            raise ValueError("Product filters are only valid for product intent.")
        return self


ROUTER_SYSTEM_PROMPT = f"""
Classify one Vietnamese e-commerce customer message and extract only facts
explicitly supported by that message. Return the required structured response.

Intent:
- product: product discovery, recommendation, or product availability/price.
- policy: store policy questions such as shipping, returns, or warranty.
- order_closing: placing, changing, cancelling, or paying for an order.
- complaint: dissatisfaction or a service/product complaint.
- smalltalk: greeting, thanks, or casual conversation without a store request.

Collection must be exactly products for product intent, policies for policy
intent, and null for order_closing, complaint, or smalltalk.
For product/policy retrieval, early_response must be null. For other intents,
provide a short, helpful Vietnamese early_response.

Normalize product categories to the exact allowed Qdrant values below; never
invent a category. Return null if the message does not identify a category.
{CATEGORY_GUIDE}

All prices are whole Vietnamese dong (VND). Interpret natural expressions such
as "5 triệu", "5 củ", and "5tr" as 5,000,000 VND. A strict upper bound such as
"dưới/chưa tới/ít hơn 5 triệu" means max_price=5,000,000 and
max_price_exclusive=true. An inclusive bound such as "tối đa/không quá/đến
5 triệu" means max_price=5,000,000 and max_price_exclusive=false. Apply the
same rule to strict lower bounds ("trên/hơn") using min_price_exclusive=true,
and inclusive lower bounds ("từ/ít nhất") using false. The application
normalizes strict bounds to inclusive whole-VND filters (for example, an
exclusive upper bound of 5,000,000 becomes 4,999,999). Use null when no price
bound is mentioned.

Set in_stock_only true only for an explicit request for available/in-stock
products. Extract a room size only when stated; room_area_m2 is in square
meters. It means the product must support a room at least that large.
Do not infer a category, budget, inventory preference, or room size that the
customer did not state. Use null for absent numeric values and false for an
absent inventory constraint.
""".strip()


def _get_structured_router():
    from src.config import groq_llm, llm, with_groq_fallback

    primary = llm.with_structured_output(
        QueryRouteExtraction,
        method="json_schema",
    )
    fallback = (
        groq_llm.with_structured_output(
            QueryRouteExtraction,
            method="function_calling",
        )
        if groq_llm is not None
        else None
    )
    return with_groq_fallback(primary, fallback)


def _normalized_metadata(metadata: QueryMetadata) -> Dict[str, Any]:
    minimum = metadata.min_price
    maximum = metadata.max_price
    if minimum is not None and metadata.min_price_exclusive:
        minimum += 1
    if maximum is not None and metadata.max_price_exclusive:
        maximum -= 1
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("Extracted price range has no valid whole-VND values.")
    return {
        "category": metadata.category,
        "in_stock_only": metadata.in_stock_only,
        "min_price": minimum,
        "max_price": maximum,
        "room_area_m2": metadata.room_area_m2,
    }


def _routing_error(exc: Exception) -> Dict[str, Any]:
    logger.exception("Gemini query routing failed")
    return {
        "intent": None,
        "collection": None,
        "metadata": None,
        "early_response": (
            "Xin lỗi, hiện em chưa phân tích được yêu cầu. "
            "Anh/chị vui lòng thử lại sau ạ."
        ),
        "status": "error",
        "error": f"query routing unavailable ({type(exc).__name__}).",
    }


def route(raw_query: str) -> Dict[str, Any]:
    """Classify and extract a query using Gemini structured JSON output."""
    try:
        if not isinstance(raw_query, str) or not raw_query.strip():
            raise ValueError("A non-empty customer query is required.")

        response = _get_structured_router().invoke(
            [
                ("system", ROUTER_SYSTEM_PROMPT),
                ("human", raw_query),
            ]
        )
        extraction = (
            response
            if isinstance(response, QueryRouteExtraction)
            else QueryRouteExtraction.model_validate(response)
        )
        return {
            "intent": extraction.intent,
            "collection": extraction.collection,
            "metadata": _normalized_metadata(extraction.metadata),
            "early_response": extraction.early_response,
        }
    except Exception as exc:
        return _routing_error(exc)
