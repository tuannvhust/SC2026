# src/tools/tool_repository.py

from typing import Any, Dict, List, Literal, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

PaymentMethod = Literal["COD", "bank", "momo", "zalopay"]

OrderUpdateAction = Literal[
    "exchange_size",
    "exchange_product",
    "return",
    "update_address",
]

Channel = Literal[
    "hotline",
    "chat_fanpage",
    "zalo_oa",
    "web_chat",
    "other",
]

EscalationReason = Literal[
    "cau_hoi_y_te",
    "ngoai_pham_vi_tai_lieu",
    "khach_yeu_cau_gap_nguoi",
    "khieu_nai_nghiem_trong",
    "loi_he_thong",
    "khach_mat_kien_nhan",
    "khac",
]

Sentiment = Literal[
    "binh_thuong",
    "hai_long",
    "kho_chiu",
    "gian",
]


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------

class CRMGetCustomerInput(BaseModel):
    phone: Optional[str] = Field(
        default=None,
        description="Customer phone number",
    )
    zalo_id: Optional[str] = Field(
        default=None,
        description="Zalo ID",
    )
    fb_id: Optional[str] = Field(
        default=None,
        description="Facebook ID",
    )
    on: Optional[str] = Field(
        default=None,
        description="Call date (YYYY-MM-DD)",
    )


@tool("crm.get_customer", args_schema=CRMGetCustomerInput)
def crm_get_customer(
    phone: Optional[str] = None,
    zalo_id: Optional[str] = None,
    fb_id: Optional[str] = None,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Look up a customer by phone or channel identity."""

    return {
        "found": bool(phone or zalo_id or fb_id),
        "customer_id": "CUST-1029" if phone else None,
        "name": "Khách hàng",
        "honorific": "Anh/Chị",
        "phone": phone,
        "identities": {
            "zalo_id": zalo_id,
            "fb_id": fb_id,
        },
        "orders": [],
        "ambiguous": False,
        "sessions": [],
    }


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class CatalogSearchInput(BaseModel):
    query: Optional[str] = Field(
        default=None,
        description="Product search query",
    )
    category: Optional[str] = Field(
        default=None,
        description="Product category",
    )
    sku: Optional[str] = Field(
        default=None,
        description="Product SKU",
    )
    max_price_vnd: Optional[int] = Field(
        default=None,
        description="Maximum price in VND",
    )
    min_room_area_m2: Optional[int] = Field(
        default=None,
        description="Minimum room coverage in square meters",
    )
    on: Optional[str] = Field(
        default=None,
        description="Call date (YYYY-MM-DD)",
    )


@tool("catalog.search", args_schema=CatalogSearchInput)
def catalog_search(
    query: Optional[str] = None,
    category: Optional[str] = None,
    sku: Optional[str] = None,
    max_price_vnd: Optional[int] = None,
    min_room_area_m2: Optional[int] = None,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Search the product catalog."""

    return {
        "items": [
            {
                "sku": sku or "SKU-AIR-PRO",
                "name": "Máy lọc không khí Pro",
                "list_price_vnd": 4_890_000,
                "attributes": {
                    "coverage_m2": 30,
                },
                "variants": [],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class InventoryCheckInput(BaseModel):
    sku: str = Field(
        description="SKU or variant SKU",
    )
    on: Optional[str] = Field(
        default=None,
        description="Inventory date (YYYY-MM-DD)",
    )


@tool("inventory.check", args_schema=InventoryCheckInput)
def inventory_check(
    sku: str,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Check product inventory."""

    return {
        "sku": sku,
        "in_stock": True,
        "qty": 15,
        "restock_expected": None,
        "discontinued": False,
        "successor_sku": None,
    }


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

class PricingGetQuoteInput(BaseModel):
    sku: str = Field(
        description="Product SKU",
    )
    on: Optional[str] = Field(
        default=None,
        description="Pricing date (YYYY-MM-DD)",
    )
    qty: Optional[int] = Field(
        default=1,
        description="Quantity",
    )
    customer_phone: Optional[str] = Field(
        default=None,
        description="Customer phone for customer-specific promotions",
    )
    address: Optional[str] = Field(
        default=None,
        description="Delivery address for regional promotions",
    )
    basket_skus: Optional[List[str]] = Field(
        default=None,
        description="Other SKUs in the same basket",
    )


@tool("pricing.get_quote", args_schema=PricingGetQuoteInput)
def pricing_get_quote(
    sku: str,
    on: Optional[str] = None,
    qty: Optional[int] = 1,
    customer_phone: Optional[str] = None,
    address: Optional[str] = None,
    basket_skus: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Calculate the final price and applicable promotions."""

    return {
        "list_price_vnd": 4_890_000,
        "final_price_vnd": 4_401_000,
        "applied_promos": ["PROMO-10PCT"],
        "expired_promos": [],
        "ineligible_promos": [],
        "not_applied_exclusive": [],
        "freeship": True,
    }


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------

class OrderCreateInput(BaseModel):
    customer_phone: str = Field(
        description="Customer phone number",
    )
    sku: str = Field(
        description="Product SKU",
    )
    qty: int = Field(
        description="Order quantity",
    )
    price_vnd: int = Field(
        description="Final price after valid promotions",
    )
    promo_code: Optional[str] = Field(
        default=None,
        description="Applied promotion code",
    )
    payment: PaymentMethod = Field(
        description="Payment method",
    )
    address: Optional[str] = Field(
        default=None,
        description="Delivery address",
    )
    on: Optional[str] = Field(
        default=None,
        description="Order date (YYYY-MM-DD)",
    )


@tool("order.create", args_schema=OrderCreateInput)
def order_create(
    customer_phone: str,
    sku: str,
    qty: int,
    price_vnd: int,
    payment: PaymentMethod,
    promo_code: Optional[str] = None,
    address: Optional[str] = None,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new order."""

    return {
        "order_id": "ORD-2026-999",
        "status": "created",
        "error": None,
        "estimated_delivery": "2026-10-10",
    }


# ---------------------------------------------------------------------------
# Order update
# ---------------------------------------------------------------------------

class OrderUpdateInput(BaseModel):
    order_id: str = Field(
        description="Order ID",
    )
    action: OrderUpdateAction = Field(
        description="Order update action",
    )
    new_variant_sku: Optional[str] = Field(
        default=None,
        description="New variant SKU",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for the update",
    )
    on: Optional[str] = Field(
        default=None,
        description="Update date (YYYY-MM-DD)",
    )


@tool("order.update", args_schema=OrderUpdateInput)
def order_update(
    order_id: str,
    action: OrderUpdateAction,
    new_variant_sku: Optional[str] = None,
    reason: Optional[str] = None,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Update, exchange, or return an existing order."""

    return {
        "order_id": order_id,
        "status": "updated",
        "fee_vnd": 0,
    }


# ---------------------------------------------------------------------------
# Order status (M2)
# ---------------------------------------------------------------------------

class OrderStatusInput(BaseModel):
    order_id: Optional[str] = Field(
        default=None,
        description="Order ID",
    )
    customer_phone: Optional[str] = Field(
        default=None,
        description="Customer phone number",
    )
    on: Optional[str] = Field(
        default=None,
        description="Query date (YYYY-MM-DD)",
    )


@tool("order.status", args_schema=OrderStatusInput)
def order_status(
    order_id: Optional[str] = None,
    customer_phone: Optional[str] = None,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve the status of customer orders."""

    return {
        "orders": []
    }


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

class ScheduleCallbackInput(BaseModel):
    customer_phone: str = Field(
        description="Customer phone number",
    )
    callback_at: str = Field(
        description="Callback time in ISO datetime format",
    )
    note: Optional[str] = Field(
        default=None,
        description="Callback note",
    )
    on: Optional[str] = Field(
        default=None,
        description="Date the callback was created (YYYY-MM-DD)",
    )


@tool("schedule.callback", args_schema=ScheduleCallbackInput)
def schedule_callback(
    customer_phone: str,
    callback_at: str,
    note: Optional[str] = None,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Schedule a callback."""

    return {
        "callback_id": "CB-1002",
        "moved_from": None,
    }


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------

class HandoffBrief(BaseModel):
    customer_phone: str = Field(
        pattern=r"^0[0-9]{9}$",
    )
    customer_name: Optional[str]
    customer_id: Optional[str] = None

    channel: Optional[Channel] = None

    escalation_reason: EscalationReason
    escalation_reason_detail: Optional[str] = None

    conversation_summary: str = Field(
        min_length=20,
        max_length=800,
    )

    product_advised: Optional[str]
    price_quoted_vnd: Optional[int]
    promo_code: Optional[str] = None

    facts_confirmed: Dict[str, Any] = Field(
        default_factory=dict,
    )
    open_questions: List[str] = Field(
        default_factory=list,
    )

    sentiment: Optional[Sentiment] = None

    next_action: str

    history_refs: List[str] = Field(
        default_factory=list,
    )

    generated_at: str


class HandoffTransferInput(BaseModel):
    brief: HandoffBrief
    on: Optional[str] = Field(
        default=None,
        description="Handoff date (YYYY-MM-DD)",
    )


@tool("handoff.transfer", args_schema=HandoffTransferInput)
def handoff_transfer(
    brief: HandoffBrief,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Transfer the conversation to a human agent."""

    return {
        "ticket_id": "TICKET-8888",
        "status": "queued",
    }


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryReadInput(BaseModel):
    key: str = Field(
        description="Memory key",
    )
    on: Optional[str] = Field(
        default=None,
        description="Query date (YYYY-MM-DD)",
    )


@tool("memory.read", args_schema=MemoryReadInput)
def memory_read(
    key: str,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Read data from customer memory."""

    return {
        "key": key,
        "value": None,
    }


class MemoryWriteInput(BaseModel):
    key: str = Field(
        description="Memory key",
    )
    value: Any = Field(
        description="Value to store",
    )
    provenance_session_id: Optional[str] = Field(
        default=None,
        description="Session that produced this fact",
    )
    on: Optional[str] = Field(
        default=None,
        description="Write date (YYYY-MM-DD)",
    )


@tool("memory.write", args_schema=MemoryWriteInput)
def memory_write(
    key: str,
    value: Any,
    provenance_session_id: Optional[str] = None,
    on: Optional[str] = None,
) -> Dict[str, Any]:
    """Queue an explicit profile fact for commit when the session ends."""

    return {
        "status": "queued_for_session_commit",
        "key": key,
        "provenance_session_id": provenance_session_id,
    }


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

M1_TOOLS = [
    crm_get_customer,
    catalog_search,
    inventory_check,
    pricing_get_quote,
    order_create,
    order_update,
    schedule_callback,
    handoff_transfer,
    memory_read,
    memory_write,
]

M2_TOOLS = [
    order_status,
]

ALL_TOOLS = M1_TOOLS + M2_TOOLS