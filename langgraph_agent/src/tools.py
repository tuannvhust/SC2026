"""BTC-compatible, data-backed tool adapters."""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
REF_DATE = "2026-10-15"


def _load(name: str):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


PRODUCTS = _load("catalog/products.json")
PRODUCTS = PRODUCTS.get("products", PRODUCTS) if isinstance(PRODUCTS, dict) else PRODUCTS
PRODUCT_BY_SKU = {p["sku"]: p for p in PRODUCTS}
PROMOTIONS = _load("catalog/promotions.json")
PROMOTIONS = PROMOTIONS.get("promotions", PROMOTIONS) if isinstance(PROMOTIONS, dict) else PROMOTIONS
INVENTORY = _load("catalog/inventory_timeline.json")
CRM = _load("catalog/crm_seed.json")["customers"]

# Compatibility export for the original prototype.
CATALOG = {p["sku"]: {"name": p["name"], "price_vnd": p.get("list_price_vnd", 0),
                       "in_stock": p.get("stock", 0) > 0, "delivery_days": 2, "promos": []}
           for p in PRODUCTS}

POLICY_DIR = DATA / "policy"


def policy_kb_search(query: str = "", top_k: int = 3, **_) -> list[Dict[str, Any]]:
    """Deterministic policy retriever; replaceable by a vector retriever in production."""
    tokens = {t.lower() for t in re.findall(r"[\wÀ-ỹ]+", query) if len(t) > 2}
    hits = []
    for path in POLICY_DIR.glob("*.md"):
        if "NOI-BO" in path.name.upper() or "noi-quy" in path.name.lower():
            continue
        content = path.read_text(encoding="utf-8")
        score = sum(content.lower().count(token) for token in tokens)
        if score:
            hits.append({"chunk_id": path.stem, "source": path.name, "score": score,
                         "text": content[:700].replace("\n", " ")})
    return sorted(hits, key=lambda item: item["score"], reverse=True)[:top_k]


def _region(address: str | None) -> str | None:
    s = (address or "").lower()
    if any(x in s for x in ("hcm", "sài gòn", "sai gon", "cần thơ", "can tho")): return "nam"
    if any(x in s for x in ("hà nội", "ha noi", "đống đa", "dong da")): return "bac"
    return None


def crm_get_customer(phone=None, zalo_id=None, fb_id=None, **_) -> Dict[str, Any]:
    pairs = (("phone", phone), ("zalo_id", zalo_id), ("fb_id", fb_id))
    matches = [c for c in CRM if any(v and c.get(k) == v for k, v in pairs)]
    if not matches:
        return {"found": False, "customer_id": None, "name": None, "honorific": None,
                "phone": phone, "identities": {}, "orders": [], "sessions": [], "ambiguous": False}
    ambiguous = len(matches) > 1
    c = matches[0]
    return {"found": True, "customer_id": None if ambiguous else c["customer_id"],
            "name": None if ambiguous else c.get("name"), "honorific": None if ambiguous else c.get("honorific"),
            "phone": c.get("phone"), "identities": {k: c.get(k) for k in ("phone", "zalo_id", "fb_id")},
            "orders": [] if ambiguous else c.get("orders", []), "sessions": [] if ambiguous else c.get("sessions", []),
            "ambiguous": ambiguous,
            "candidates": [{"customer_id": x["customer_id"], "name": x.get("name"), "honorific": x.get("honorific")} for x in matches]}


def catalog_search(query=None, category=None, sku=None, max_price_vnd=None, min_room_area_m2=None,
                   include_discontinued=False, **_) -> list[Dict[str, Any]]:
    q = (query or "").lower(); out = []
    for p in PRODUCTS:
        hay = " ".join(str(p.get(x, "")) for x in ("sku", "name", "brand", "category")).lower()
        if sku and sku not in p["sku"]: continue
        tokens = [t for t in re.findall(r"[\wÀ-ỹ]+", q) if len(t) > 2]
        if q and q not in hay and not any(a.lower() in q for a in p.get("aliases", [])) and not any(t in hay for t in tokens): continue
        if category and category.lower() not in p.get("category", "").lower(): continue
        if max_price_vnd is not None and p.get("list_price_vnd", 0) > max_price_vnd: continue
        if min_room_area_m2 is not None and p.get("attributes", {}).get("room_area_m2", 0) < min_room_area_m2: continue
        out.append({"sku": p["sku"], "name": p["name"], "list_price_vnd": p.get("list_price_vnd", 0),
                    "attributes": p.get("attributes", {}), "variants": p.get("variants", [])})
    return out


def inventory_check(sku: str, on: str = REF_DATE, **_) -> Dict[str, Any]:
    events = [e for e in INVENTORY.get("events", []) if e["sku"] == sku and e["date"] <= on]
    p = PRODUCT_BY_SKU.get(sku, {}); qty = events[-1]["qty"] if events else p.get("stock", 0)
    future = [e["date"] for e in INVENTORY.get("events", []) if e["sku"] == sku and e["date"] > on and e["qty"] > 0]
    return {"sku": sku, "in_stock": qty > 0, "qty": qty, "restock_expected": min(future, default=None),
            "discontinued": bool(p.get("discontinued", False)), "successor_sku": p.get("successor_sku")}


_ONCE_USED = set()


def pricing_get_quote(sku: str, on: str = REF_DATE, qty: int = 1, customer_phone=None,
                      address=None, basket_skus=None, **_) -> Dict[str, Any]:
    p = PRODUCT_BY_SKU[sku]
    variant = next((v for v in p.get("variants", []) if v.get("sku") == sku), None)
    base = p.get("list_price_vnd", 0) + (variant or {}).get("price_delta_vnd", 0)
    candidates=[]; expired=[]; ineligible=[]
    for promo in PROMOTIONS:
        targets = promo.get("applies_to", []); hit = "*" in targets or p["sku"] in targets
        hit = hit or any(t.startswith("category:") and p.get("category", "").startswith(t.split(":", 1)[1]) for t in targets)
        if not hit: continue
        if on < promo["start"]: ineligible.append({"promo_code": promo["promo_code"], "reason": "not_started"})
        elif on > promo["end"]: expired.append(promo["promo_code"])
        else:
            cond = promo.get("conditions", {}); why = None
            if cond.get("min_qty") and qty + len(basket_skus or []) < cond["min_qty"]: why = "min_qty"
            if cond.get("exclude_variant_size") and variant and variant.get("size") in cond["exclude_variant_size"]: why = "exclude_variant_size"
            if cond.get("region") and _region(address) not in cond["region"]: why = "region"
            if cond.get("requires_owned_sku") and not any(cond["requires_owned_sku"] in o.get("sku", "") for c in CRM if c.get("phone") == customer_phone for o in c.get("orders", [])): why = "requires_owned_sku"
            if cond.get("once_per_customer") and (customer_phone, promo["promo_code"]) in _ONCE_USED: why = "once_per_customer"
            if promo.get("min_order_vnd") and base < promo["min_order_vnd"]: why = "min_order"
            if why: ineligible.append({"promo_code": promo["promo_code"], "reason": why}); continue
            if promo.get("type") == "fixed": discount = promo.get("discount_vnd", 0)
            elif promo.get("type") == "percent": discount = int(base * promo.get("discount_percent", 0) / 100)
            else: discount = 0
            candidates.append((promo, discount))
    exclusive = [(p, d) for p, d in candidates if not p.get("stackable")]
    stackable = [(p, d) for p, d in candidates if p.get("stackable")]
    best = max(exclusive, key=lambda x: x[1], default=None)
    applied_items = stackable + ([best] if best else [])
    final = base - (best[1] if best else 0)
    applied = [{"promo_code": p["promo_code"], "type": p.get("type"), "discount_vnd": d, **({"gift_sku": p["gift_sku"]} if p.get("gift_sku") else {})} for p, d in applied_items]
    return {"sku": sku, "list_price_vnd": base, "final_price_vnd": final, "applied_promos": applied,
            "expired_promos": expired, "ineligible_promos": ineligible,
            "not_applied_exclusive": [p["promo_code"] for p, _ in exclusive if best and p["promo_code"] != best[0]["promo_code"]],
            "freeship": _region(address) == "nam" or base >= 2000000,
            "_internal_price_floor_vnd": int(p.get("list_price_vnd", 0) * 0.9)}


def order_create(customer_phone: str, sku: str, qty: int = 1, price_vnd: int | None = None,
                 promo_code=None, payment="COD", address=None, on: str = REF_DATE, basket_skus=None, **_) -> Dict[str, Any]:
    stock = inventory_check(sku, on); quote = pricing_get_quote(sku, on, qty, customer_phone, address, basket_skus)
    if not stock["in_stock"] or stock["qty"] < qty: return {"error": "out_of_stock", "sku": sku}
    if price_vnd != quote["final_price_vnd"]: return {"error": "price_mismatch", "expected_price_vnd": quote["final_price_vnd"]}
    return {"order_id": "ORD-" + uuid.uuid4().hex[:6].upper(), "status": "created", "sku": sku,
            "price_vnd": price_vnd, "estimated_delivery": (date.fromisoformat(on) + timedelta(days=2)).isoformat()}


def order_status(order_id=None, customer_phone=None, **_) -> Dict[str, Any]:
    orders = [o for c in CRM if not customer_phone or c.get("phone") == customer_phone for o in c.get("orders", [])]
    return {"orders": [o for o in orders if not order_id or o.get("order_id") == order_id]}


def order_update(order_id: str, action: str, new_variant_sku=None, reason=None, on=REF_DATE, **_) -> Dict[str, Any]:
    return {"order_id": order_id, "status": "updated", "fee_vnd": 0}


def schedule_callback(customer_phone: str, callback_at: str, note=None, **_) -> Dict[str, Any]:
    return {"callback_id": "CB-" + uuid.uuid4().hex[:8], "moved_from": None, "callback_at": callback_at}


def handoff_transfer(brief: Dict[str, Any], **_) -> Dict[str, Any]:
    return {"ticket_id": "TKT-" + uuid.uuid4().hex[:8], "status": "queued"}


def mask_pii(text: str) -> str:
    return re.sub(r"(?<!\d)0\d{9}(?!\d)", "<PHONE>", text)


TOOLS = {"crm.get_customer": crm_get_customer, "catalog.search": catalog_search, "inventory.check": inventory_check,
         "pricing.get_quote": pricing_get_quote, "order.create": order_create, "order.status": order_status,
         "order.update": order_update, "schedule.callback": schedule_callback, "handoff.transfer": handoff_transfer,
         "catalog_search": lambda query, **kw: [{**x, "price_vnd": x["list_price_vnd"], "active_promos": []} for x in catalog_search(query, **kw)],
         "order_create": order_create}
TOOLS["policy_kb.search"] = policy_kb_search
DEFAULT_CATALOG_SEARCH = TOOLS["catalog_search"]


def tool_crm_get_customer(customer_phone: str, **kwargs):
    r = crm_get_customer(phone=customer_phone, **kwargs)
    return {**r, "customer_id": r.get("customer_id"), "is_returning_customer": r.get("found", False) and not r.get("ambiguous", False),
            "profile": {}, "episodic_summaries": r.get("sessions", [])}
