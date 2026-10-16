# src/tools/tool_repository.py

import logging
import os
import time
from datetime import date
from threading import Lock
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field
try:
    from supabase import Client, ClientOptions, create_client
except ImportError:
    Client = Any  # type: ignore
    ClientOptions = None  # type: ignore
    create_client = None  # type: ignore

load_dotenv()

logger = logging.getLogger(__name__)
supabase: Optional[Any] = None
_supabase_lock = Lock()
SUPABASE_QUERY_RETRIES = 2
SUPABASE_RETRY_DELAY_SECONDS = 0.25
SUPABASE_POSTGREST_TIMEOUT_SECONDS = 10.0


def _create_supabase_client(url: str, key: str) -> Any:
    if create_client is None or ClientOptions is None:
        raise RuntimeError("supabase package is not installed. Run `pip install supabase`.")
    options = ClientOptions(
        postgrest_client_timeout=httpx.Timeout(
            SUPABASE_POSTGREST_TIMEOUT_SECONDS,
            connect=5.0,
        )
    )
    return create_client(url, key, options=options)


def _execute_supabase_query(query: Any) -> Any:
    """Retry transient transport failures for idempotent Supabase read queries."""
    for attempt in range(SUPABASE_QUERY_RETRIES + 1):
        try:
            return query.execute()
        except httpx.TransportError:
            if attempt >= SUPABASE_QUERY_RETRIES:
                raise
            delay = SUPABASE_RETRY_DELAY_SECONDS * (2 ** attempt)
            logger.warning(
                "Transient Supabase transport failure; retrying read query "
                "(attempt %s/%s) after %.2fs.",
                attempt + 1,
                SUPABASE_QUERY_RETRIES,
                delay,
                exc_info=True,
            )
            time.sleep(delay)


def _get_supabase() -> Any:
    global supabase
    if create_client is None:
        raise RuntimeError("supabase package is not installed. Run `pip install supabase`.")
    if supabase is None:
        with _supabase_lock:
            if supabase is None:
                url = _get_supabase_project_url()
                key = os.getenv("SUPABASE_KEY", "").strip()
                if not url or not key:
                    raise RuntimeError(
                        "Supabase catalog access requires SUPABASE_KEY and either "
                        "SUPABASE_URL or a direct Supabase "
                        "SUPABASE_DATABASE_URL (db.<project-ref>.supabase.co)."
                    )
                supabase = _create_supabase_client(url, key)
    return supabase


def _get_supabase_project_url() -> str:
    """Return the REST project URL, deriving it only from a direct DB endpoint."""
    project_url = os.getenv("SUPABASE_URL", "").strip()
    if project_url:
        return project_url

    database_url = os.getenv("SUPABASE_DATABASE_URL", "").strip()
    hostname = urlsplit(database_url).hostname if database_url else None
    suffix = ".supabase.co"
    if hostname and hostname.startswith("db.") and hostname.endswith(suffix):
        project_ref = hostname[len("db.") : -len(suffix)]
        if project_ref:
            return f"https://{project_ref}{suffix}"
    return ""


if create_client and _get_supabase_project_url() and os.getenv("SUPABASE_KEY", "").strip():
    supabase = _create_supabase_client(
        _get_supabase_project_url(),
        os.environ["SUPABASE_KEY"].strip(),
    )


_catalog_engine = None
_catalog_reranker = None
_catalog_lock = Lock()


def _get_catalog_components():
    global _catalog_engine, _catalog_reranker
    if _catalog_engine is None or _catalog_reranker is None:
        with _catalog_lock:
            if _catalog_engine is None or _catalog_reranker is None:
                from src.memory.semantic_rag.hybrid_search import HybridSearchEngine
                from src.memory.semantic_rag.reranker import Reranker

                _catalog_engine = HybridSearchEngine()
                _catalog_reranker = Reranker()
    return _catalog_engine, _catalog_reranker


def _rows(response: Any) -> List[Dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        raise RuntimeError("Supabase returned an invalid table response.")
    return [row for row in data if isinstance(row, dict)]


def filter_catalog_candidates(
    candidates: List[Dict[str, Any]],
    *,
    min_price_vnd: Optional[int] = None,
    max_price_vnd: Optional[int] = None,
    in_stock_only: bool = False,
) -> List[Dict[str, Any]]:
    """Apply realtime price and stock constraints to static Qdrant candidates."""
    if not candidates or (
        min_price_vnd is None
        and max_price_vnd is None
        and not in_stock_only
    ):
        return candidates

    candidate_skus = list(
        dict.fromkeys(
            str(item["sku"])
            for item in candidates
            if item.get("sku")
        )
    )
    if not candidate_skus:
        return []

    client = _get_supabase()
    products = _rows(
        _execute_supabase_query(
            client.table("products")
            .select("*")
            .in_("sku", candidate_skus)
        )
    )
    variants = _rows(
        _execute_supabase_query(
            client.table("product_variants")
            .select("*")
            .in_("product_sku", candidate_skus)
        )
    )
    products_by_sku = {
        str(product.get("sku")): product
        for product in products
        if product.get("sku")
    }
    variants_by_sku: Dict[str, List[Dict[str, Any]]] = {}
    for variant in variants:
        parent_sku = str(variant.get("product_sku") or "")
        if parent_sku:
            variants_by_sku.setdefault(parent_sku, []).append(variant)

    filtered: List[Dict[str, Any]] = []
    for candidate in candidates:
        sku = str(candidate.get("sku") or "")
        product = products_by_sku.get(sku)
        if product is None:
            continue

        base_price = int(product.get("list_price_vnd") or 0)
        product_variants = variants_by_sku.get(sku, [])
        if product_variants:
            options = [
                (
                    base_price + int(variant.get("price_delta_vnd") or 0),
                    int(variant.get("stock", 0) or 0),
                )
                for variant in product_variants
            ]
        else:
            options = [
                (
                    base_price,
                    int(product.get("stock", product.get("total_stock", 0)) or 0),
                )
            ]

        matching_options = [
            (price, stock)
            for price, stock in options
            if (min_price_vnd is None or price >= min_price_vnd)
            and (max_price_vnd is None or price <= max_price_vnd)
            and (not in_stock_only or stock > 0)
        ]
        if not matching_options:
            continue

        enriched = dict(candidate)
        enriched["list_price_vnd"] = base_price
        enriched["total_stock"] = sum(stock for _, stock in options)
        enriched["in_stock"] = enriched["total_stock"] > 0
        if min_price_vnd is not None or max_price_vnd is not None:
            enriched["matching_price_vnd"] = min(
                price for price, _ in matching_options
            )
        filtered.append(enriched)
    return filtered


def _promotions_for_product(
    promotions: List[Dict[str, Any]],
    sku: str,
    category: Optional[str],
) -> List[Dict[str, Any]]:
    applicable = []
    category_target = f"category:{category}" if category else None
    for promo in promotions:
        targets = promo.get("applies_to") or []
        if isinstance(targets, str):
            targets = [targets]
        category_targets = [
            str(target).removeprefix("category:")
            for target in targets
            if isinstance(target, str) and target.startswith("category:")
        ]
        category_match = category and any(
            category == target or category.startswith(f"{target}/")
            for target in category_targets
        )
        if "*" in targets or sku in targets or category_match:
            applicable.append(promo)
    return applicable


def _address_region(address: Optional[str]) -> Optional[str]:
    if not address:
        return None
    normalized = address.casefold()
    if any(word in normalized for word in ("miền nam", "tp.hcm", "hồ chí minh", "cần thơ")):
        return "nam"
    if any(word in normalized for word in ("miền bắc", "hà nội", "hải phòng")):
        return "bac"
    if any(word in normalized for word in ("miền trung", "đà nẵng", "huế")):
        return "trung"
    return None


def _evaluate_promotion_conditions(
    promo: Dict[str, Any],
    *,
    order_total: int,
    qty: int,
    address: Optional[str],
    variant_size: Any,
    customer_phone: Optional[str],
) -> Optional[str]:
    conditions = promo.get("conditions") or {}
    min_order = promo.get("min_order_vnd", conditions.get("min_order_vnd"))
    if min_order is not None and order_total < int(min_order):
        return f"minimum_order_vnd:{int(min_order)}"

    min_qty = conditions.get("min_qty")
    if min_qty is not None and qty < int(min_qty):
        return f"minimum_quantity:{int(min_qty)}"

    regions = conditions.get("region")
    if regions:
        expected_regions = [regions] if isinstance(regions, str) else regions
        actual_region = _address_region(address)
        if actual_region not in expected_regions:
            return "region_not_eligible"

    excluded_sizes = conditions.get("exclude_variant_size") or []
    if variant_size is not None and variant_size in excluded_sizes:
        return f"variant_size_excluded:{variant_size}"
    if excluded_sizes and variant_size is None:
        return "variant_size_required_to_verify"

    if conditions.get("requires_owned_sku"):
        return "ownership_not_verifiable"
    if conditions.get("once_per_customer"):
        if not customer_phone:
            return "customer_phone_required"
        return "usage_limit_not_verifiable"
    return None


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
    """Find products semantically, then hydrate and filter with live Supabase data."""
    try:
        engine, reranker = _get_catalog_components()
        search_query = query or sku or category
        if not search_query:
            return {"items": [], "error": "query, sku, or category is required."}

        candidates = engine.search_products(
            str(search_query),
            top_k=30,
            category=category,
        )
        if sku:
            exact = engine.get_by_sku(sku)
            if exact and all(item.get("sku") != sku for item in candidates):
                candidates.insert(0, exact)
            candidates = [
                item for item in candidates
                if item.get("sku") == sku
                or any(
                    variant.get("variant_sku") == sku
                    for variant in item.get("variants", [])
                    if isinstance(variant, dict)
                )
            ]
        ranked = reranker.rerank(str(search_query), candidates, top_n=len(candidates))
        candidate_skus = list(
            dict.fromkeys(
                str(item["sku"]) for item in ranked if item.get("sku")
            )
        )
        if not candidate_skus:
            return {"items": []}

        client = _get_supabase()
        products = _rows(
            _execute_supabase_query(
                client.table("products")
                .select("*")
                .in_("sku", candidate_skus)
            )
        )
        variants = _rows(
            _execute_supabase_query(
                client.table("product_variants")
                .select("*")
                .in_("product_sku", candidate_skus)
            )
        )
        variants_by_sku: Dict[str, List[Dict[str, Any]]] = {}
        for variant in variants:
            parent_sku = str(variant.get("product_sku") or "")
            if parent_sku:
                variants_by_sku.setdefault(parent_sku, []).append(variant)

        products_by_sku = {str(product.get("sku")): product for product in products}
        hydrated = []
        for candidate in ranked:
            product_sku = str(candidate.get("sku") or "")
            product = products_by_sku.get(product_sku)
            if not product:
                continue
            current_variants = variants_by_sku.get(product_sku, [])
            product_attributes = product.get("attributes") or candidate.get("attributes") or {}
            if not isinstance(product_attributes, dict):
                product_attributes = {}
            if category and product.get("category") != category:
                continue
            if min_room_area_m2 is not None:
                area = product_attributes.get(
                    "room_area_m2",
                    product_attributes.get("coverage_m2"),
                )
                if area is None or float(area) < min_room_area_m2:
                    continue

            list_price = int(product.get("list_price_vnd") or 0)
            live_variants = [
                {
                    "variant_sku": variant.get("variant_sku"),
                    "size": variant.get("size"),
                    "color": variant.get("color"),
                    "stock": variant.get("stock", 0),
                    "price_delta_vnd": variant.get("price_delta_vnd", 0),
                }
                for variant in current_variants
            ]
            possible_prices = [
                list_price + int(variant.get("price_delta_vnd") or 0)
                for variant in current_variants
            ] or [list_price]
            if max_price_vnd is not None and min(possible_prices) > max_price_vnd:
                continue

            total_stock = sum(int(item.get("stock") or 0) for item in current_variants)
            if not current_variants:
                total_stock = int(product.get("stock", product.get("total_stock", 0)) or 0)
            hydrated.append(
                {
                    "sku": product_sku,
                    "name": product.get("name") or candidate.get("name"),
                    "category": product.get("category") or candidate.get("category"),
                    "brand": product.get("brand") or candidate.get("brand"),
                    "list_price_vnd": list_price,
                    "total_stock": total_stock,
                    "in_stock": total_stock > 0,
                    "attributes": product_attributes,
                    "variants": live_variants,
                }
            )
        return {"items": format_catalog_results(hydrated)}
    except Exception as exc:
        logger.exception("catalog.search failed")
        return {"items": [], "status": "error", "error": f"catalog search unavailable ({type(exc).__name__})."}


def format_catalog_results(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep catalog tool output compact so large database rows stay out of messages."""
    compact_items = []
    for item in raw_items:
        attributes = item.get("attributes") or {}
        if not isinstance(attributes, dict):
            attributes = {}
        compact_items.append(
            {
                "sku": item.get("sku"),
                "name": item.get("name"),
                "price": item.get("list_price_vnd"),
                "in_stock": item.get("in_stock"),
                "area_m2": attributes.get("room_area_m2"),
                "features": attributes.get("features"),
            }
        )
    return compact_items


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
    """Read current product or variant stock from Supabase."""
    try:
        client = _get_supabase()
        variant_rows = _rows(
            _execute_supabase_query(
                client.table("product_variants")
                .select("*")
                .eq("variant_sku", sku)
                .limit(1)
            )
        )
        if variant_rows:
            item = variant_rows[0]
        else:
            product_rows = _rows(
                _execute_supabase_query(
                    client.table("products")
                    .select("*")
                    .eq("sku", sku)
                    .limit(1)
                )
            )
            if not product_rows:
                return {"sku": sku, "status": "not_found", "error": "SKU not found."}
            item = product_rows[0]

        qty = int(item.get("stock", item.get("total_stock", 0)) or 0)
        return {
            "sku": sku,
            "in_stock": qty > 0,
            "qty": qty,
            "restock_expected": item.get("restock_expected"),
            "discontinued": bool(item.get("discontinued", False)),
            "successor_sku": item.get("successor_sku"),
        }
    except Exception as exc:
        logger.exception("inventory.check failed for SKU %s", sku)
        return {
            "sku": sku,
            "status": "error",
            "error": f"inventory lookup unavailable ({type(exc).__name__}).",
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
    """Quote current Supabase price and classify all matching promotions."""
    try:
        client = _get_supabase()
        variant_rows = _rows(
            _execute_supabase_query(
                client.table("product_variants")
                .select("*")
                .eq("variant_sku", sku)
                .limit(1)
            )
        )
        variant = variant_rows[0] if variant_rows else None
        product_sku = (
            str(variant.get("product_sku"))
            if variant and variant.get("product_sku")
            else sku
        )
        products = _rows(
            _execute_supabase_query(
                client.table("products")
                .select("*")
                .eq("sku", product_sku)
                .limit(1)
            )
        )
        if not products:
            return {"sku": sku, "status": "not_found", "error": "SKU not found."}

        product = products[0]
        list_price = int(product.get("list_price_vnd") or 0)
        if variant:
            list_price += int(variant.get("price_delta_vnd") or 0)
        quantity = max(1, int(qty or 1))
        basket_products = []
        if basket_skus:
            basket_products = _rows(
                _execute_supabase_query(
                    client.table("products")
                    .select("sku,category,list_price_vnd")
                    .in_("sku", basket_skus)
                )
            )
        basket_prices = [
            int(item.get("list_price_vnd") or 0)
            for item in basket_products
        ]
        basket_qty = quantity + len(basket_skus or [])

        promotion_rows = _rows(
            _execute_supabase_query(
                client.table("promotions").select("*")
            )
        )
        quote_date = date.fromisoformat(on) if on else date.today()
        category = product.get("category")
        matching_promotions = _promotions_for_product(
            promotion_rows,
            product_sku,
            category,
        )
        applicable_now = []
        expired_promos = []
        ineligible_promos = []
        order_total = list_price * quantity + sum(basket_prices)

        for promo in matching_promotions:
            code = str(promo.get("promo_code") or "")
            start_value = promo.get("start_date") or promo.get("start")
            end_value = promo.get("end_date") or promo.get("end")
            try:
                start_date = date.fromisoformat(str(start_value)[:10])
                end_date = date.fromisoformat(str(end_value)[:10])
            except (TypeError, ValueError):
                raise RuntimeError(f"Promotion {code or '<unknown>'} has invalid dates.")
            if quote_date < start_date or quote_date > end_date:
                expired_promos.append(code)
                continue

            reason = _evaluate_promotion_conditions(
                promo,
                order_total=order_total,
                qty=basket_qty,
                address=address,
                variant_size=variant.get("size") if variant else None,
                customer_phone=customer_phone,
            )
            if reason:
                ineligible_promos.append({"promo_code": code, "reason": reason})
                continue
            if (
                promo.get("type") == "percent_second_item"
                and (
                    basket_qty < 2
                    or (
                        basket_prices
                        and list_price > min(basket_prices)
                    )
                )
            ):
                ineligible_promos.append(
                    {"promo_code": code, "reason": "cheaper_second_item_not_in_quote"}
                )
                continue
            applicable_now.append(promo)

        # Gift promotions stack by default unless explicitly restricted
        stackable_promos = [
            promo for promo in applicable_now
            if promo.get("stackable") or promo.get("type") == "gift"
        ]
        exclusive_promos = [
            promo for promo in applicable_now
            if not promo.get("stackable") and promo.get("type") != "gift"
        ]

        def discount_amount(promo: Dict[str, Any]) -> int:
            promo_type = promo.get("type")
            if promo_type == "fixed":
                return min(list_price, int(promo.get("discount_vnd") or 0))
            if promo_type == "percent":
                percent = float(promo.get("discount_percent") or 0)
                return min(list_price, int(list_price * percent / 100))
            if promo_type == "percent_second_item" and basket_qty >= 2:
                percent = float(promo.get("discount_percent") or 0)
                return min(list_price, int(list_price * percent / 100))
            return 0

        best_exclusive = (
            max(exclusive_promos, key=discount_amount)
            if exclusive_promos
            else None
        )
        applied = list(stackable_promos)
        if best_exclusive:
            applied.append(best_exclusive)
        not_applied_exclusive = [
            str(promo.get("promo_code"))
            for promo in exclusive_promos
            if promo is not best_exclusive
        ]
        total_discount = sum(discount_amount(promo) for promo in applied)
        gifts = [
            {"promo_code": promo.get("promo_code"), "sku": promo.get("gift_sku")}
            for promo in applied
            if promo.get("type") == "gift" and promo.get("gift_sku")
        ]
        return {
            "sku": sku,
            "list_price_vnd": list_price,
            "final_price_vnd": max(0, list_price - total_discount),
            "discount_vnd": total_discount,
            "applied_promos": [
                str(promo.get("promo_code"))
                for promo in applied
                if promo.get("promo_code")
            ],
            "expired_promos": expired_promos,
            "ineligible_promos": ineligible_promos,
            "not_applied_exclusive": not_applied_exclusive,
            "gifts": gifts,
            "freeship": any(promo.get("type") == "freeship" for promo in applied),
        }
    except Exception as exc:
        logger.exception("pricing.get_quote failed for SKU %s", sku)
        return {
            "sku": sku,
            "status": "error",
            "error": f"pricing lookup unavailable ({type(exc).__name__}).",
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
        description=(
            "A JSON object/dictionary mapping confirmed fact names to values. "
            "Pass an object, not a string containing serialized JSON."
        ),
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
    """Transfer to a human agent; brief.facts_confirmed must be a JSON object."""

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
