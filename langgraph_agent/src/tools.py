from datetime import date, datetime
from typing import Any, Dict, List

from .memory import db, get_or_create_customer, load_episodic, load_profile

CATALOG = {
    "SKU-AP-X": {
        "name": "Máy lọc không khí X",
        "aliases": ["máy lọc", "lọc không khí", "may loc"],
        "price_vnd": 4_890_000,
        "in_stock": True,
        "delivery_days": 2,
        "promos": [{"code": "GIFT-FILTER", "desc": "Tặng bộ lọc", "valid_to": "2026-10-31"}],
    },
    "SKU-AP-Y": {
        "name": "Máy lọc không khí Y",
        "aliases": ["máy lọc y"],
        "price_vnd": 5_200_000,
        "in_stock": True,
        "delivery_days": 3,
        "promos": [{"code": "OLD-SALE", "desc": "Giảm 300k", "valid_to": "2026-03-16"}],  # hết hạn
    },
}


def tool_crm_get_customer(customer_phone: str) -> Dict[str, Any]:
    cid, returning = get_or_create_customer(customer_phone)
    return {
        "customer_id": cid,
        "is_returning_customer": returning,
        "profile": load_profile(cid),
        "episodic_summaries": load_episodic(cid),
    }


def tool_catalog_search(query: str) -> List[Dict[str, Any]]:
    """Trả về giá + CHỈ CÁC khuyến mãi còn hiệu lực hôm nay. Đây là nguồn duy nhất cung cấp giá bán."""
    today = date.today()
    q = query.lower()
    out = []
    for sku, p in CATALOG.items():
        hit = sku.lower() in q or p["name"].lower() in q or any(a in q for a in p["aliases"])
        if not hit:
            continue
        active = [x for x in p["promos"] if date.fromisoformat(x["valid_to"]) >= today]
        out.append({
            "sku": sku,
            "name": p["name"],
            "price_vnd": p["price_vnd"],
            "in_stock": p["in_stock"],
            "delivery_days": p["delivery_days"],
            "active_promos": active,
        })
    return out


def tool_order_create(customer_id: str, sku: str, price_vnd: int, **kwargs) -> Dict[str, Any]:
    item = CATALOG.get(sku)
    if item is None:
        raise ValueError(f"unknown sku {sku}")
    if price_vnd != item["price_vnd"]:  # không bao giờ âm thầm tạo đơn hàng bị lệch giá so với catalog
        raise ValueError(f"price mismatch: got {price_vnd}, catalog {item['price_vnd']}")
    order_id = "ORD-" + datetime.now().strftime("%y%m%d%H%M%S")
    with db() as c:
        c.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?)",
            (order_id, customer_id, sku, price_vnd, datetime.now().isoformat()),
        )
    return {"order_id": order_id, "sku": sku, "price_vnd": price_vnd, "status": "created"}


TOOLS = {
    "catalog_search": tool_catalog_search,
    "order_create": tool_order_create,
}
