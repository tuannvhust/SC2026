"""Read-only data endpoints for the four reference pages."""
import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from src.tools import tool_repository

router = APIRouter(prefix="/reference", tags=["Reference data"])
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
REFERENCE_DATE = "2026-10-15"
PUBLIC_POLICY_FILES = {
    "thong-bao-lich-nghi.md",
    "quy-trinh-cod-hoan-hang.md",
    "faq.md",
    "dieu-khoan-khuyen-mai.md",
    "chinh-sach-van-chuyen-thanh-toan.md",
    "chinh-sach-doi-tra.md",
    "chinh-sach-doi-tra-v2026-06-het-hieu-luc.md",
    "chinh-sach-bao-hanh.md",
}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mask_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return f"{digits[:2]}•••••{digits[-3:]}" if len(digits) >= 7 else "Not provided"


def _mask_email(value: Any) -> str:
    value = str(value or "")
    if "@" not in value:
        return "Not provided"
    name, domain = value.split("@", 1)
    return f"{name[:1]}•••@{domain}"


def _date_text(value: Any) -> str:
    return str(value or "")[:10]


def _promotion_status(start: Any, end: Any) -> str:
    start_date, end_date = _date_text(start), _date_text(end)
    return "Upcoming" if start_date and REFERENCE_DATE < start_date else "Expired" if end_date and REFERENCE_DATE > end_date else "Active"


def _customer(row: dict[str, Any], count: int = 0, latest: str | None = None) -> dict[str, Any]:
    name = str(row.get("full_name") or row.get("preferred_name") or row.get("name") or "Customer")
    return {
        "id": str(row.get("customer_id") or row.get("id") or ""), "name": name,
        "initials": "".join(part[0] for part in name.split()[:2]).upper(),
        "phone": _mask_phone(row.get("phone")), "email": _mask_email(row.get("email")),
        "segment": "Returning customer" if count else "Customer",
        "verified": bool(row.get("phone_verified", row.get("verified", False))),
        "caseCount": count, "latestActivity": latest,
    }


def _repo_customers() -> list[dict[str, Any]]:
    return [_customer(row) for row in _json(DATA / "catalog" / "crm_seed.json").get("customers", [])]


@router.get("/customers")
def customers(q: str = "", page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100)):
    source = "backend"
    try:
        engine = tool_repository._get_crm_engine()
        with engine.connect() as connection:
            rows = connection.execute(tool_repository.text(
                "SELECT c.customer_id, c.full_name, c.preferred_name, c.phone, c.email, "
                "c.phone_verified, COUNT(s.session_id) AS session_count, "
                "MAX(s.last_activity_at) AS latest_activity "
                "FROM public.customers c LEFT JOIN public.conversation_sessions s "
                "ON s.customer_id = c.customer_id WHERE c.deleted_at IS NULL "
                "AND c.status IN ('active','provisional') GROUP BY c.customer_id "
                "ORDER BY MAX(s.last_activity_at) DESC NULLS LAST, c.customer_id"
            )).mappings().all()
        items = [_customer(dict(row), int(row["session_count"] or 0), str(row["latest_activity"]) if row["latest_activity"] else None) for row in rows]
    except Exception as error:
        logger.info("CRM directory unavailable; using repository data: %s", type(error).__name__)
        source = "repository"
        items = _repo_customers()
    if q.strip():
        query = q.strip().casefold()
        items = [row for row in items if query in " ".join(str(row.get(k, "")) for k in ("id", "name", "phone", "email")).casefold()]
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "source": source, "page": page, "page_size": page_size, "total": total}


def _repo_products() -> list[dict[str, Any]]:
    catalog = _json(DATA / "catalog" / "products.json")
    result = []
    for i, p in enumerate(catalog.get("products", []), 1):
        stock = int(p.get("stock") or 0)
        attrs = p.get("attributes") or {}
        result.append({"id": p.get("sku", f"PRD-{i:03}"), "sku": p.get("sku", ""), "name": p.get("name", ""), "category": p.get("category", "Other"), "price": p.get("list_price_vnd", 0), "availability": "Out of stock" if stock == 0 else "Low stock" if stock <= 5 else "In stock", "stock": stock, "description": str(attrs.get("features", p.get("brand", ""))), "features": str(attrs.get("features", "")).split(", ") if attrs.get("features") else [], "warranty": f"{attrs.get('warranty_months', 0)} months", "tags": [], "icon": "▤"})
    return result


@router.get("/products")
def products():
    try:
        client = tool_repository._get_supabase()
        products = tool_repository._rows(tool_repository._execute_supabase_query(client.table("products").select("*")))
        variants = tool_repository._rows(tool_repository._execute_supabase_query(client.table("product_variants").select("*")))
        by_parent: dict[str, list[dict[str, Any]]] = {}
        for variant in variants:
            by_parent.setdefault(str(variant.get("product_sku") or ""), []).append(variant)
        items = []
        for p in products:
            sku = str(p.get("sku") or "")
            product_variants = by_parent.get(sku, [])
            stock = sum(int(v.get("stock") or 0) for v in product_variants) if product_variants else int(p.get("stock") or p.get("total_stock") or 0)
            attrs = p.get("attributes") if isinstance(p.get("attributes"), dict) else {}
            features = attrs.get("features") or p.get("features") or p.get("description") or ""
            warranty = attrs.get("warranty_months") or p.get("warranty")
            items.append({"id": sku, "sku": sku, "name": p.get("name") or sku, "category": p.get("category") or "Other", "price": int(p.get("list_price_vnd") or 0), "availability": "Out of stock" if stock == 0 else "Low stock" if stock <= 5 else "In stock", "stock": stock, "description": str(features), "features": features if isinstance(features, list) else ([str(features)] if features else []), "warranty": f"{warranty} months" if isinstance(warranty, (int, float)) else str(warranty or "See policy"), "tags": [], "icon": "▤"})
        return {"items": items, "source": "backend"}
    except Exception as error:
        logger.info("Supabase products unavailable; using repository data: %s", type(error).__name__)
        return {"items": _repo_products(), "source": "repository"}


def _repo_promotions() -> list[dict[str, Any]]:
    data = _json(DATA / "catalog" / "promotions.json")
    result = []
    for i, p in enumerate(data.get("promotions", []), 1):
        start, end = _date_text(p.get("start")), _date_text(p.get("end"))
        status = _promotion_status(start, end)
        amount = p.get("discount_percent")
        value = f"{amount}%" if amount else f"{int(p.get('discount_vnd') or 0):,}đ" if p.get("discount_vnd") else "Gift offer"
        result.append({"id": p.get("promo_code", f"PROMO-{i:03}"), "code": p.get("promo_code", ""), "name": p.get("name", ""), "type": p.get("type", ""), "status": status, "value": value, "start": start, "end": end, "minimum": int(p.get("min_order_vnd") or 0), "products": p.get("applies_to", []), "description": p.get("description") or p.get("name", ""), "terms": [f"Minimum quantity: {p['conditions']['min_qty']}" ] if (p.get("conditions") or {}).get("min_qty") else [], "icon": "%"})
    return result


@router.get("/promotions")
def promotions():
    try:
        rows = tool_repository._get_all_promotions(tool_repository._get_supabase())
        items = []
        for i, p in enumerate(rows, 1):
            start, end = _date_text(p.get("start_date") or p.get("start")), _date_text(p.get("end_date") or p.get("end"))
            status = _promotion_status(start, end)
            discount = p.get("discount_percent")
            value = f"{discount}%" if discount else f"{int(p.get('discount_vnd') or 0):,}đ" if p.get("discount_vnd") else "Gift offer"
            applies = p.get("applies_to") or p.get("product_skus") or []
            items.append({"id": p.get("promo_code") or p.get("code") or f"PROMO-{i:03}", "code": p.get("promo_code") or p.get("code") or "", "name": p.get("name") or p.get("description") or "Promotion", "type": p.get("type") or "Offer", "status": status, "value": value, "start": start, "end": end, "minimum": int(p.get("min_order_vnd") or p.get("minimum_order_vnd") or 0), "products": applies if isinstance(applies, list) else [], "description": p.get("description") or p.get("name") or "", "terms": [], "icon": "%"})
        return {"items": items, "source": "backend", "reference_date": REFERENCE_DATE}
    except Exception as error:
        logger.info("Supabase promotions unavailable; using repository data: %s", type(error).__name__)
        return {"items": _repo_promotions(), "source": "repository", "reference_date": REFERENCE_DATE}


def _repo_policies() -> list[dict[str, Any]]:
    items = []
    for path in sorted((DATA / "policy").glob("*.md")):
        name = path.name.lower()
        if name not in PUBLIC_POLICY_FILES:
            continue
        content = path.read_text(encoding="utf-8")
        title = path.stem.replace("-", " ").title()
        archived = "het-hieu-luc" in name
        items.append({"id": path.stem, "topic": title, "category": "Archived" if archived else "Store policy", "version": "1.0", "status": "Archived" if archived else "Current", "effective": "Historical" if archived else "Current", "effectiveTo": "" if not archived else "Archived", "published": "", "owner": "Store policy", "approvedBy": "", "summary": next((line.lstrip("# ") for line in content.splitlines() if line.strip()), title), "keywords": [], "content": content, "changeNote": ""})
    return items


@router.get("/policies")
def policies():
    try:
        items = _repo_policies()
        return {"items": items, "source": "backend"}
    except Exception as error:
        logger.exception("Policy corpus unavailable: %s", type(error).__name__)
        return {"items": [], "source": "repository"}
