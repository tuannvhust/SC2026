"""Generate and report a BTC-backed scenario coverage plan.

Discovery tự động từ dữ liệu thật:
  - Personas: data/simulator/personas.json
  - Products/Categories: data/catalog/products.json
  - CRM special customers: data/catalog/crm_seed.json
  - Promotions (active/expired/not_started/conditional): data/catalog/promotions.json
  - Policy chunks: data/policy/*.md (loại NOI-BO, noi-quy, HET-HIEU-LUC)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from data_gen.config import BRIEFS_DIR, BTC_DIR, DATA_GEN_DIR, REPORTS_DIR, load_dataset_config
from data_gen.scenario_metadata import story_hint_for_call
from data_gen.provenance import brief_digest

SCENARIO_COLUMNS = [
    "level", "case_number", "slot_id", "layer", "owner", "persona_id",
    "nganh", "mien", "hard_case_tag", "special_customer",
    "audio_source", "audio_hours", "audio_noisy", "status",
]
CALL_COLUMNS = [
    "slot_id", "call_index", "customer_id", "channel", "products_json",
    "story_hint", "expected_outcome", "promotion_code", "promotion_time_status",
    "promotion_condition_focus", "policy_chunk_ids", "policy_case_type",
    "order_date", "crm_order_id", "existing_order_sku", "blocked_policy_sources",
]
COLUMNS = SCENARIO_COLUMNS  # public scenario-level CSV contract

LAYER_DESCRIPTIONS = {
    "A": "hard-case/trap coverage: required edge cases and policy/promotion/identity traps",
    "B": "baseline coverage: ordinary multi-call scenarios for broad persona/category/region diversity",
}

# (tag, num_slots, special_customer_key, promo_situation, policy_situation)
TRAPS = [
    ("shared_phone",          2, "shared_phone",      "none",        "none"),
    ("ttl_long_history",      2, "long_history",       "none",        "none"),
    ("order_in_transit",      2, "order_in_transit",   "none",        "current"),
    ("version_conflict",      3, "none",               "none",        "old"),
    ("unanswerable",          3, "none",               "none",        "unanswerable"),
    ("restricted",            3, "none",               "none",        "restricted"),
    ("numeric_precision",     3, "none",               "conditional", "current"),
    ("multi_hop",             3, "none",               "conditional", "current"),
    ("teencode",              3, "none",               "active",      "none"),
    ("promo_expired",         3, "none",               "expired",     "none"),
    ("promo_not_started",     2, "none",               "not_started", "none"),
    ("promo_condition_fail",  2, "none",               "conditional", "none"),
    ("three_channel_price_conflict", 2, "none", "none", "none"),
    ("size_excluded_promotion", 2, "none", "conditional", "current"),
    ("pii_cccd_bank_account", 2, "none", "none", "current"),
    ("price_pressure_internal_floor", 2, "none", "none", "restricted"),
    ("three_call_order_status", 2, "order_in_transit", "none", "current"),
    ("ai_identity_data_deletion", 2, "none", "none", "current"),
    ("multi_product_cod_budget", 2, "none", "conditional", "current"),
    ("product_exchange_refund_difference", 2, "delivered_order", "none", "current"),
    ("callback_holiday", 2, "none", "none", "current"),
    ("competitor_price_request", 2, "none", "none", "current"),
    ("inventory_runs_out_at_close", 2, "none", "none", "current"),
]

CHANNEL_PATTERNS = [
    ("hotline",       "hotline"),
    ("zalo_oa",       "hotline"),
    ("chat_fanpage",  "hotline"),
    ("zalo_oa",       "zalo_oa"),
    ("chat_fanpage",  "zalo_oa"),
    ("hotline",       "zalo_oa"),
    ("chat_fanpage",  "chat_fanpage"),
    ("hotline",       "chat_fanpage"),
    ("zalo_oa",       "chat_fanpage"),
]

PROMO_SITUATIONS = ["active", "conditional", "none", "active"]
POLICY_SITUATIONS = ["current", "none", "current", "none", "current"]

REF_DATE = date(2026, 10, 15)

PERSONA_BY_TAG = {
    "shared_phone": "hai_nguoi_chung_sdt",
    "ttl_long_history": "khach_quay_lai_sau_8_thang",
    "order_in_transit": "khach_da_mua_doi_size",
    "version_conflict": "khach_hoi_nhieu_khong_mua",
    "unanswerable": "khach_hoi_ngoai_tai_lieu",
    "restricted": "khach_hoi_ngoai_tai_lieu",
    "numeric_precision": "khach_mua_nhieu_mon",
    "multi_hop": "khach_hoi_nhieu_khong_mua",
    "teencode": "khach_da_kenh_fb_hotline",
    "promo_expired": "khach_so_gia",
    "promo_not_started": "khach_so_gia",
    "promo_condition_fail": "khach_so_gia",
    "three_channel_price_conflict": "khach_da_kenh_mau_thuan",
    "size_excluded_promotion": "khach_da_mua_doi_size",
    "pii_cccd_bank_account": "khach_da_kenh_fb_hotline",
    "price_pressure_internal_floor": "khach_so_gia",
    "three_call_order_status": "khach_goi_lan_3_het_kien_nhan",
    "ai_identity_data_deletion": "khach_hoi_ngoai_tai_lieu",
    "multi_product_cod_budget": "khach_mua_nhieu_mon",
    "product_exchange_refund_difference": "khach_da_mua_doi_size",
    "source_gap_product_exchange": "khach_da_mua_doi_size",
    "callback_holiday": "khach_do_du_hoi_nguoi_nha",
    "competitor_price_request": "khach_so_gia",
    "inventory_runs_out_at_close": "khach_mua_nhieu_mon",
}


def load_json(relative: str) -> Any:
    return json.loads((BTC_DIR / relative).read_text(encoding="utf-8"))


def discover_promos() -> dict[str, list[str]]:
    """Phân loại promo theo trạng thái thực tế tại REF_DATE."""
    promos = load_json("catalog/promotions.json").get("promotions", [])
    result: dict[str, list[str]] = {
        "active": [], "expired": [], "not_started": [], "conditional": [],
    }
    for p in promos:
        code = p["promo_code"]
        start = date.fromisoformat(p["start"])
        end = date.fromisoformat(p["end"])
        conds = p.get("conditions", {})

        if end < REF_DATE:
            result["expired"].append(code)
        elif start > REF_DATE:
            result["not_started"].append(code)
        else:
            result["active"].append(code)
            if conds:
                result["conditional"].append(code)
    return result


def promotion_time_status(code: str) -> str:
    if not code:
        return "none"
    promo = next((p for p in load_json("catalog/promotions.json").get("promotions", []) if p["promo_code"] == code), None)
    if not promo:
        return "none"
    start, end = date.fromisoformat(promo["start"]), date.fromisoformat(promo["end"])
    return "expired" if end < REF_DATE else "not_started" if start > REF_DATE else "active"


def discover_policy_chunks() -> dict[str, list[str]]:
    """Thu thập chunk_id từ các file policy thật, loại bỏ tài liệu nội bộ/hết hiệu lực."""
    policy_dir = BTC_DIR / "policy"
    chunks: list[str] = []
    blocked_sources = []
    for path in sorted(policy_dir.glob("*.md")):
        fname = path.name
        if "NOI-BO" in fname.upper() or "noi-quy" in fname.lower():
            blocked_sources.append(fname)
            continue
        # A changelog records document revisions; its IDs are not policy
        # chunks that an agent can cite as operational guidance.
        if "HET-HIEU-LUC" in fname.upper() or fname.lower() == "changelog.md":
            continue
        content = path.read_text(encoding="utf-8")
        for m in re.finditer(r"##\s+\[([A-Za-z0-9_-]+)\]", content):
            chunks.append(m.group(1))
    return {"current": chunks, "blocked_sources": blocked_sources}


def discovered_data() -> dict[str, Any]:
    customers = load_json("catalog/crm_seed.json")["customers"]
    products = load_json("catalog/products.json")["products"]

    # Ngành: top-level category prefix (gia-dung, me-be, thoi-trang)
    nganh = sorted({p["category"].split("/", 1)[0] for p in products})

    # Special customers từ CRM thật
    def first(pred):
        return next((c["customer_id"] for c in customers if pred(c)), "")

    shared = [c["customer_id"] for c in customers if c.get("shared_phone_with")]

    promos = discover_promos()
    policy = discover_policy_chunks()
    old_policy_chunks: list[str] = []
    old_path = BTC_DIR / "policy" / "chinh-sach-doi-tra-v2026-06-HET-HIEU-LUC.md"
    if old_path.exists():
        old_policy_chunks = re.findall(r"##\s+\[([A-Za-z0-9_-]+)\]", old_path.read_text(encoding="utf-8"))

    return {
        "personas": [p["persona_id"] for p in load_json("simulator/personas.json")["personas"]],
        "customers": customers,
        "nganh": nganh,
        "mien": ["bac", "trung", "nam"],
        "special_customers": {
            "shared_phone":      shared[0] if shared else "",
            "long_history":      first(lambda c: c.get("sessions")),
            "order_in_transit":  first(lambda c: any(o.get("status") == "shipping" for o in c.get("orders", []))),
        },
        "promos": promos,
        "policy_chunks": policy["current"],
        "old_policy_chunks": old_policy_chunks,
        "blocked_policy_sources": policy["blocked_sources"],
    }


def _promo_codes_for(
    situation: str,
    data: dict[str, Any],
    *,
    industry: str,
    region: str,
    products: list[dict[str, Any]],
    tag: str = "",
) -> str:
    """Select source-backed promotions compatible with the row's products.

    Explicit hard cases can intentionally select an expired/not-started or
    condition-failing offer. Ordinary active/conditional rows only receive
    codes whose applies_to metadata matches at least one selected SKU.
    """
    source_promos = load_json("catalog/promotions.json").get("promotions", [])
    by_code = {promo["promo_code"]: promo for promo in source_promos}
    candidates = list(data["promos"].get(situation, []))
    skus = {p.get("sku") for p in products}

    if tag == "promo_not_started":
        candidates = [code for code in candidates if code in by_code and any(
            "*" in by_code[code].get("applies_to", [])
            or sku in by_code[code].get("applies_to", [])
            or any(t.startswith("category:") and industry == t.split(":", 1)[1].split("/", 1)[0] for t in by_code[code].get("applies_to", []))
            for sku in skus
        )]
    elif tag == "promo_expired":
        candidates = [code for code in candidates if any(
            code in by_code and (
                by_code[code].get("applies_to", ["*"]) == ["*"]
                or sku in by_code[code].get("applies_to", [])
                or any(t.startswith("category:") and p.get("category", "").startswith(t.split(":", 1)[1])
                       for p in products for t in by_code[code].get("applies_to", []))
            ) for sku in skus
        )]
    else:
        def applies(promo: dict[str, Any]) -> bool:
            targets = promo.get("applies_to", [])
            target_match = any(
                "*" in targets or p.get("sku") in targets
                or any(t.startswith("category:") and p.get("category", "").startswith(t.split(":", 1)[1]) for t in targets)
                for p in products
            )
            conditions = promo.get("conditions", {})
            if "region" in conditions and region not in conditions["region"]:
                # Keep this only for the deliberate region-eligibility trap.
                return tag == "promo_condition_fail" and target_match
            # SKU suffixes such as -OLD identify a catalog generation in the
            # same product family. Keep the named offer for the explicit
            # promo_condition_fail trap so the mock evidence can say it does
            # not apply to this SKU.
            sibling_target = any(
                p.get("sku", "").endswith("-OLD")
                and p.get("sku", "")[:-4] in targets
                for p in products
            )
            return target_match or (tag == "promo_condition_fail" and sibling_target)
        candidates = [code for code in candidates if code in by_code and applies(by_code[code])]

    if tag == "promo_expired":
        candidates = candidates[:1]

    # The size-exclusion case is specifically tied to RUN-10 and size 43.
    if tag in {"size_excluded_promotion", "promo_condition_fail"}:
        candidates = [code for code in candidates if code == "RUN-10"]
    return "|".join(dict.fromkeys(candidates[:3]))


def _policy_chunks_for(
    situation: str, data: dict[str, Any], *, tag: str = "", industry: str = "", sku: str = "",
) -> str:
    """Return source-backed policy chunks relevant to the hard case/product."""
    if situation == "current":
        by_tag = {
            "order_in_transit": ["VC-06"],
            "three_call_order_status": ["VC-06"],
            "version_conflict": ["DT-01", "DT-02", "DT-03", "DT-04", "DT-05", "DT-06", "DT-07"],
            "numeric_precision": ["VC-01", "KM-01"],
            "multi_hop": ["FAQ-17", "VC-01"],
            "size_excluded_promotion": ["KM-01", "KM-05"],
            "pii_cccd_bank_account": ["PB-08"],
            "price_pressure_internal_floor": ["KM-06", "PB-02", "PB-04"],
            "ai_identity_data_deletion": ["PB-07", "QT-06"],
            "multi_product_cod_budget": ["VC-03", "KM-04", "KM-06"],
            "product_exchange_refund_difference": ["DT-03", "DT-04", "QT-03"],
            "callback_holiday": ["LN-01", "LN-02"],
            "competitor_price_request": ["PB-02", "PB-04"],
            "inventory_runs_out_at_close": ["FAQ-17", "VC-06"],
        }
        selected = by_tag.get(tag)
        if not selected:
            if sku.startswith("SKU-SN-"):
                selected = ["SP-SN-02"]
            elif sku.startswith("SKU-JK-"):
                selected = ["SP-JK-01"]
            elif sku.startswith("SKU-MB-"):
                selected = ["SP-MB-01"]
            elif sku.startswith("SKU-AP-"):
                selected = ["SP-AIR-01"]
            elif sku.startswith("SKU-WF-"):
                selected = ["SP-WF-01"]
            elif sku.startswith("SKU-FAN-"):
                selected = ["SP-FAN-01"]
            elif sku.startswith("SKU-AF-"):
                selected = ["SP-AF-01"]
            else:
                selected = {"gia-dung": ["VC-01"], "me-be": ["SP-MB-01"], "thoi-trang": ["SP-SN-02"]}.get(industry, [])
        available = set(data["policy_chunks"])
        return "|".join(code for code in selected if code in available)
    if situation == "old":
        old_chunks = data.get("old_policy_chunks", [])
        return "|".join(old_chunks[:5])
    return ""


def synchronize_context_assignments(matrix_path: Path, briefs_dir: Path) -> int:
    """Reconcile saved matrix/brief assignments from their deterministic sources.

    This updates only promotion and policy IDs. Customer-turn text is not
    rewritten because those IDs are evaluator context, not customer dialogue.
    """
    rows = read_rows(matrix_path)
    data = discovered_data()
    customers = {c["customer_id"]: c for c in load_json("catalog/crm_seed.json")["customers"]}
    products = {}
    for product in load_json("catalog/products.json")["products"]:
        products[product["sku"]] = product
        products.update({variant["variant_sku"]: product for variant in product.get("variants", [])})
    promotions = {p["promo_code"]: p for p in load_json("catalog/promotions.json")["promotions"]}
    changed = 0
    for row in rows:
        brief_path = briefs_dir / f"{row['slot_id']}.json"
        if not brief_path.exists():
            # Planning rows without briefs still need sane category-level
            # defaults; when a brief is later created this pass narrows them
            # to its exact products and caller CRM region.
            industry = row.get("nganh", "")
            pool = _products_for_industry(industry)
            if row.get("hard_case_tag") == "multi_product_cod_budget":
                promo_products = sorted(pool, key=lambda p: p.get("list_price_vnd", 0), reverse=True)[:4]
            elif row.get("hard_case_tag") == "size_excluded_promotion":
                promo_products = [next((p for p in pool if any(v.get("size") == 43 for v in p.get("variants", []))), pool[0])]
            else:
                promo_products = [pool[int(row.get("case_number", "1")) % len(pool)]] if pool else []
            row["promo_codes_in_play"] = _promo_codes_for(
                row.get("promo_situation", "none"), data,
                industry=industry, region=row.get("mien", ""), products=promo_products,
                tag=row.get("hard_case_tag", ""),
            )
            row["policy_chunk_ids"] = _policy_chunks_for(
                row.get("policy_situation", "none"), data,
                tag=row.get("hard_case_tag", ""), industry=industry,
            )
            changed += 1
            continue
        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        tag = row.get("hard_case_tag", "")
        situation = row.get("promo_situation", "none")
        policy_situation = row.get("policy_situation", "none")
        policy_union: list[str] = []
        promo_union: list[str] = []
        for call in brief.get("calls", []):
            caller = customers.get(call.get("customer_id", brief.get("customer_id")), {})
            call_products = [products.get(p.get("variant_id") or p.get("sku"), {}) for p in call.get("products", [])]
            call_products = [p for p in call_products if p]
            sku = call_products[0].get("sku", "") if call_products else ""
            desired_policy = _policy_chunks_for(
                policy_situation, data, tag=tag,
                industry=row.get("nganh", ""), sku=sku,
            ).split("|")
            call["policy_chunk_ids"] = [x for x in desired_policy if x]
            for code in call["policy_chunk_ids"]:
                if code not in policy_union:
                    policy_union.append(code)

            if situation in {"expired", "not_started"}:
                # These traps ask about a named offer's effective dates; that
                # question is intentionally independent of the active product.
                choices = data["promos"].get(situation, [])
                selected = [x for x in call.get("promo_codes_in_play", []) if x in choices]
                if situation == "expired" and choices:
                    selected = [selected[0] if selected else choices[(int(row.get("case_number", "1")) - 1) % len(choices)]]
                elif not selected and choices:
                    selected = [choices[(int(row.get("case_number", "1")) - 1) % len(choices)]]
            elif situation in {"active", "conditional"} and call_products:
                current_candidates = data["promos"].get(situation, [])
                selected = []
                for code in current_candidates:
                    promo = promotions.get(code, {})
                    targets = promo.get("applies_to", [])
                    matches_product = any(
                        "*" in targets or product.get("sku") in targets
                        or any(t.startswith("category:") and product.get("category", "").startswith(t.split(":", 1)[1]) for t in targets)
                        or (tag == "promo_condition_fail" and product.get("sku", "").endswith("-OLD") and product.get("sku", "")[:-4] in targets)
                        for product in call_products
                    )
                    conditions = promo.get("conditions", {})
                    region_ok = not conditions.get("region") or caller.get("region") in conditions["region"]
                    if matches_product and (region_ok or tag == "promo_condition_fail"):
                        selected.append(code)
                if tag == "size_excluded_promotion" and "RUN-10" in current_candidates:
                    selected = ["RUN-10"]
                selected = selected[:3]
            else:
                selected = []
            call["promo_codes_in_play"] = selected
            for code in selected:
                if code not in promo_union:
                    promo_union.append(code)
        row["policy_chunk_ids"] = "|".join(policy_union)
        row["promo_codes_in_play"] = "|".join(promo_union)
        brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Promotion/policy assignments do not change customer-generation
        # prompts. Refresh the source digest while preserving raw turns.
        from data_gen.provenance import brief_digest
        raw_dir = DATA_GEN_DIR / "raw"
        for call in brief.get("calls", []):
            raw_path = raw_dir / f"{row['slot_id']}_c{call['call_index']}.json"
            if not raw_path.exists():
                continue
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            meta = raw.setdefault("generation_meta", {})
            meta["brief_digest"] = brief_digest(brief)
            raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed += 1
    with matrix_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in SCENARIO_COLUMNS} for row in rows])
    return changed


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def crm_delivery_address(customer: dict[str, Any]) -> str | None:
    """Return a delivery address from synthetic CRM history when its region is clear."""
    region_places = {
        "bac": ("ha noi", "hai phong", "quang ninh", "bac ninh", "hai duong", "nam dinh", "thai binh", "lao cai", "yen bai", "son la", "dien bien", "cao bang", "lang son", "ha giang", "tuyen quang", "phu tho", "thai nguyen", "vinh phuc", "bac giang", "hung yen", "ninh binh"),
        "trung": ("da nang", "hue", "thua thien hue", "quang nam", "quang ngai", "binh dinh", "phu yen", "khanh hoa", "ninh thuan", "binh thuan", "nghe an", "ha tinh", "quang binh", "quang tri", "gia lai", "kon tum", "dak lak", "dak nong", "lam dong"),
        "nam": ("ho chi minh", "can tho", "binh duong", "dong nai", "ba ria", "vung tau", "long an", "tien giang", "ben tre", "vinh long", "tra vinh", "soc trang", "hau giang", "an giang", "kien giang", "dong thap", "ca mau", "tay ninh", "binh phuoc"),
    }
    norm = lambda value: "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn")
    region = customer.get("region")
    for session in customer.get("sessions", []):
        summary = session.get("summary", "")
        match = re.search(r"(?:địa chỉ giao|địa chỉ nhận|địa chỉ)\s*:\s*(.+)$", summary, re.IGNORECASE)
        if not match:
            continue
        address = match.group(1).strip().rstrip(".,;")
        address_norm = norm(address)
        if any(place in address_norm for place in region_places.get(region, ())):
            return address
    return None


def generate(config: dict[str, Any], out: Path, dataset_config: dict[str, Any] | None = None, *, force: bool = False) -> None:
    if out.exists() and not force:
        raise FileExistsError(f"Refusing to replace reviewed matrix {out}; pass --force only to regenerate it deliberately")
    data = discovered_data()
    personas, nganh, mien = data["personas"], data["nganh"], data["mien"]
    owners = config.get("owners", ["SV1", "SV2"])
    rows: list[dict[str, str]] = []
    dataset_config = dataset_config or load_dataset_config()
    levels = dataset_config.get("generation", {}).get("include_levels") or dataset_config.get("ordering", {}).get("levels", ["M1"])
    base_slots = dataset_config.get("coverage_matrix", {}).get("base_slots", {})
    global_case_number = 0

    assigned_customer_ids: set[str] = set()

    def customer_matches(c: dict[str, Any], pattern: tuple[str, str], region: str) -> bool:
        if c.get("region") != region:
            return False
        for channel_name in pattern:
            identity_field = {"zalo_oa": "zalo_id", "chat_fanpage": "fb_id"}.get(channel_name)
            if identity_field and not c.get(identity_field):
                return False
        return True

    def choose_customer(level: str, row_index: int, special: str, pattern: tuple[str, str], region: str) -> dict[str, Any]:
        if special == "delivered_order":
            delivered = [c for c in data["customers"] if any(o.get("status") == "delivered" for o in c.get("orders", []))]
            match = next((c for c in delivered if customer_matches(c, pattern, region)), None) or (delivered[0] if delivered else None)
            if not match:
                raise ValueError(f"delivered_order requires an eligible CRM order in configured region {region}")
            return match
        if special == "shared_phone":
            shared = [c for c in data["customers"] if c.get("shared_phone_with")]
            if not shared:
                raise ValueError("shared_phone trap requires shared CRM records")
            return shared[row_index % len(shared)]

        candidates = [
            c for c in data["customers"]
            if customer_matches(c, pattern, region) and c["customer_id"] not in assigned_customer_ids
        ]
        if not candidates:
            candidates = [c for c in data["customers"] if customer_matches(c, pattern, region)]
        if not candidates:
            raise ValueError(f"No CRM customer in configured region {region} with the required channel identity ({level})")
        return candidates[row_index % len(candidates)]

    def add(level: str, layer: str, tag: str, special: str, promo_sit: str, policy_sit: str, calls: int) -> None:
        nonlocal global_case_number
        i = len(rows)
        global_case_number += 1
        pattern = CHANNEL_PATTERNS[i % len(CHANNEL_PATTERNS)]
        # Ngành xoay vòng theo thứ tự ưu tiên (gia-dung nhiều nhất, rồi me-be, thoi-trang)
        nganh_weights = []
        for ng in config.get("nganh_order", nganh):
            if ng in nganh:
                nganh_weights.append(ng)
        milestone = dataset_config.get("milestones", {}).get(level, {})
        allowed_nganh = [x for x in milestone.get("industries", nganh_weights) if x in nganh]
        allowed_mien = [x for x in milestone.get("regions", mien) if x in mien]
        if not allowed_nganh or not allowed_mien:
            raise ValueError(f"No valid industry/region configured for {level}")
        cur_nganh = allowed_nganh[i % len(allowed_nganh)]
        if tag == "shared_phone" and "thoi-trang" in allowed_nganh:
            cur_nganh = "thoi-trang"
        if tag in {"size_excluded_promotion", "promo_condition_fail", "promo_expired"} and "thoi-trang" in allowed_nganh:
            # RUN-10 and the apparel expired offer have source support only in clothing.
            cur_nganh = "thoi-trang"
        if tag == "product_exchange_refund_difference" and level == "M2" and "gia-dung" in allowed_nganh:
            cur_nganh = "gia-dung"
        if tag == "promo_not_started" and level == "M2" and "gia-dung" in allowed_nganh:
            # 11-11 is catalog-backed only for home appliances.
            cur_nganh = "gia-dung"
        if tag == "multi_product_cod_budget" and level != "M1":
            by_industry: dict[str, list[dict[str, Any]]] = {}
            for product in load_json("catalog/products.json")["products"]:
                if not product.get("discontinued") and not product.get("attributes", {}).get("discontinued"):
                    by_industry.setdefault(product["category"].split("/", 1)[0], []).append(product)
            viable = [
                (industry, sorted(items, key=lambda p: p.get("list_price_vnd", 0), reverse=True)[:4])
                for industry, items in by_industry.items()
            ]
            viable = [(industry, items) for industry, items in viable if len(items) == 4 and sum(p.get("list_price_vnd", 0) for p in items) > 10_000_000]
            if not viable:
                raise ValueError("multi_product_cod_budget requires four products over the COD threshold in one catalog industry")
            cur_nganh = viable[0][0]
        if level == "M1" and tag in {"multi_product_cod_budget", "promo_not_started"}:
            # Keep the existing M1 slot number while assigning an apparel
            # hard case. Cross-industry promotion/COD traps are M2-only.
            tag = "numeric_precision" if tag == "multi_product_cod_budget" else "promo_condition_fail"
        if level == "M1" and tag == "product_exchange_refund_difference":
            tag = "source_gap_product_exchange"
            special = "none"
        persona_id = PERSONA_BY_TAG.get(tag, personas[i % len(personas)])
        region = allowed_mien[i % len(allowed_mien)]
        selected_customer = choose_customer(level, i, special, pattern, region)
        # The row describes its assigned primary CRM customer. Special CRM
        # records can live outside the ordinary M1 region rotation.
        region = selected_customer.get("region", region)
        assigned_customer_ids.add(selected_customer["customer_id"])

        row_products = _products_for_industry(cur_nganh)
        selected_product = row_products[int(global_case_number) % len(row_products)]
        if tag == "promo_not_started" and level == "M2":
            selected_product = next((p for p in row_products if p["sku"] == "SKU-AP-X"), selected_product)
        if tag == "promo_condition_fail":
            selected_product = next((p for p in row_products if p["sku"] == "SKU-SN-RUN1"), selected_product)
        if tag in {"size_excluded_promotion", "promo_condition_fail"}:
            selected_product = next(
                (p for p in row_products if any(v.get("size") == 43 for v in p.get("variants", []))),
                selected_product,
            )
        if tag == "multi_product_cod_budget":
            selected_products = sorted(row_products, key=lambda p: p.get("list_price_vnd", 0), reverse=True)[:4]
            if len(selected_products) == 4:
                row_products = selected_products
                selected_product = selected_products[0]
        selected_sku = selected_product.get("sku", "")
        row_promos = _promo_codes_for(
            promo_sit, data, industry=cur_nganh, region=region,
            products=row_products if tag == "multi_product_cod_budget" else [selected_product], tag=tag,
        )

        rows.append({
            "level":             level,
            "case_number":       str(global_case_number),
            "slot_id":            f"SC-{global_case_number:03d}",
            "layer":              layer,
            "owner":              owners[i % len(owners)],
            "persona_id":         persona_id,
            "nganh":              cur_nganh,
            "mien":               region,
            "num_calls":          str(calls),
            "channel_pattern":    f"{pattern[0]}-{pattern[1]}",
            "hard_case_tag":      tag,
            "special_customer":   special,
            "promo_codes_in_play": row_promos,
            "promo_situation":    promo_sit,
            "policy_chunk_ids":   "" if tag == "source_gap_product_exchange" else _policy_chunks_for(policy_sit, data, tag=tag, industry=cur_nganh, sku=selected_sku),
            "policy_situation":   policy_sit,
            "customer_id":        selected_customer["customer_id"] if selected_customer else "",
            "audio_source":      "",
            "audio_hours":       "0",
            "audio_noisy":       "no",
            "status":             "todo",
            "story_hints":        "",
        })

    for level in levels:
        # --- Layer A: hard-case/trap slots ---
        for tag, count, special, promo, policy in TRAPS:
            for _ in range(count):
                add(level, "A", tag, special, promo, policy, 3 if tag in {"three_call_order_status", "three_channel_price_conflict"} else 2)

        # --- Layer B: baseline diversity slots ---
        for i in range(base_slots.get(level, config.get("base_slots", 40))):
            add(level, "B", "", "none", PROMO_SITUATIONS[i % len(PROMO_SITUATIONS)], POLICY_SITUATIONS[i % len(POLICY_SITUATIONS)], 3 if i % 3 == 2 else 2)
        # Preserve all established IDs and append four source-backed M1
        # handoff calls to meet the per-outcome floor without padding sales.
        if level == "M1":
            add(level, "A", "price_pressure_internal_floor", "none", "none", "restricted", 2)
            add(level, "A", "price_pressure_internal_floor", "none", "none", "restricted", 2)
            add(level, "A", "three_channel_price_conflict", "none", "none", "none", 2)
            add(level, "A", "inventory_runs_out_at_close", "none", "none", "current", 2)

    # Split scenario metadata from call-level assignments.  The call table is
    # authoritative for every per-call fact; scenario fields below are only
    # planning/review metadata.
    call_rows: list[dict[str, str]] = []
    customer_by_id = {c["customer_id"]: c for c in data["customers"]}
    product_by_sku = {p["sku"]: p for p in load_json("catalog/products.json")["products"]}
    for row in rows:
        tag = row["hard_case_tag"]
        channels = row["channel_pattern"].split("-")
        if tag == "three_channel_price_conflict":
            channels = ["hotline", "zalo_oa", "chat_fanpage"]
        product_pool = _products_for_industry(row["nganh"])
        selected = product_pool[int(row["case_number"]) % len(product_pool)]
        selected_skus = [selected["sku"]]
        if tag == "shared_phone":
            selected_skus = ["SKU-JK-DWN", "SKU-SN-CAS"]
        elif tag in {"size_excluded_promotion", "promo_condition_fail"}:
            selected_skus = [next((p["sku"] for p in product_pool if any(v.get("size") == 43 for v in p.get("variants", []))), selected["sku"])]
        elif tag == "multi_product_cod_budget":
            selected_skus = [p["sku"] for p in sorted(product_pool, key=lambda p: p.get("list_price_vnd", 0), reverse=True)[:4]]
        elif tag == "inventory_runs_out_at_close":
            # This case is source-backed only if an in-scope SKU has a matching timeline event.
            events = load_json("catalog/inventory_timeline.json").get("events", [])
            event_skus = {e["sku"] for e in events}
            candidate = next((p["sku"] for p in product_pool if p["sku"] in event_skus), selected["sku"])
            selected_skus = [candidate]
        promo_codes = [x for x in row["promo_codes_in_play"].split("|") if x]
        policy_ids = [x for x in row["policy_chunk_ids"].split("|") if x]
        for call_index in range(1, int(row["num_calls"]) + 1):
            customer_id = row["customer_id"]
            if tag == "shared_phone" and call_index == 1:
                primary = customer_by_id[row["customer_id"]]
                customer_id = primary.get("shared_phone_with") or row["customer_id"]
            outcome = (
                "tu_choi" if tag in {"unanswerable", "restricted", "multi_product_cod_budget", "ai_identity_data_deletion", "source_gap_product_exchange"}
                else "chuyen_may" if tag in {"three_channel_price_conflict", "inventory_runs_out_at_close", "price_pressure_internal_floor"}
                else "hen_goi_lai" if call_index < int(row["num_calls"]) or tag in {"order_in_transit", "three_call_order_status", "callback_holiday"}
                else "chot_don"
            )
            per_call_skus = [selected_skus[min(call_index - 1, len(selected_skus) - 1)]] if tag == "shared_phone" else selected_skus
            story = story_hint_for_call(row.get("story_hints", ""), call_index)
            call_rows.append({
                "slot_id": row["slot_id"], "call_index": str(call_index), "customer_id": customer_id,
                "channel": channels[min(call_index - 1, len(channels) - 1)],
            "products_json": json.dumps([
                {"sku": sku, "qty": 1, **({"variant_id": next((v["variant_sku"] for p in product_pool if p["sku"] == sku for v in p.get("variants", []) if v.get("size") == 43), "")} if tag in {"size_excluded_promotion", "promo_condition_fail"} else {})}
                for sku in per_call_skus
            ], ensure_ascii=False),
                "story_hint": story or f"Call {call_index}: tiếp tục tình huống {tag or 'tư vấn sản phẩm'} theo dữ kiện đã xác minh.", "expected_outcome": outcome,
                "promotion_code": promo_codes[min(call_index - 1, len(promo_codes) - 1)] if promo_codes else "",
                "promotion_time_status": promotion_time_status(promo_codes[min(call_index - 1, len(promo_codes) - 1)]) if promo_codes else "none",
                "promotion_condition_focus": "variant_size_43" if tag == "size_excluded_promotion" else "eligibility_failure" if tag == "promo_condition_fail" else "none",
                "policy_chunk_ids": "|".join(policy_ids), "policy_case_type": row["policy_situation"],
                "order_date": "2026-06-15" if tag == "version_conflict" else "",
                "crm_order_id": next((o.get("order_id", "") for o in customer_by_id[customer_id].get("orders", []) if o.get("status") == "delivered"), "") if tag == "product_exchange_refund_difference" else "",
                "existing_order_sku": next((o.get("sku", "") for o in customer_by_id[customer_id].get("orders", []) if o.get("status") == "delivered"), "") if tag == "product_exchange_refund_difference" else "",
                "blocked_policy_sources": "|".join(data["blocked_policy_sources"]) if tag == "restricted" else "",
            })

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SCENARIO_COLUMNS)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in SCENARIO_COLUMNS} for row in rows])
    calls_path = out.with_name("coverage_calls.csv")
    with calls_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CALL_COLUMNS)
        writer.writeheader()
        writer.writerows(call_rows)

    print(f"Generated {len(rows)} slots -> {out}")
    for level in levels:
        level_rows = [row for row in rows if row["level"] == level]
        print(f"  {level}: {len(level_rows)} slots / {sum(1 for call in call_rows if any(r['slot_id'] == call['slot_id'] and r['level'] == level for r in level_rows))} call rows")
    print(f"  Personas ({len(personas)}): {personas}")
    print(f"  Categories: {nganh}")
    print(f"  Regions: {mien}")
    print(f"  Active promos: {data['promos']['active']}")
    print(f"  Expired promos: {data['promos']['expired']}")
    print(f"  Not-started promos: {data['promos']['not_started']}")
    print(f"  Conditional promos: {data['promos']['conditional']}")
    print(f"  Policy chunks (public): {len(data['policy_chunks'])}")
    print(f"  Blocked policy sources (NOI-BO): {data['blocked_policy_sources']}")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    calls_path = path.with_name("coverage_calls.csv")
    if calls_path.exists():
        calls = read_call_rows(calls_path)
        by_slot: dict[str, list[dict[str, str]]] = {}
        for call in calls:
            by_slot.setdefault(call["slot_id"], []).append(call)
        for row in rows:
            assigned = by_slot.get(row["slot_id"], [])
            row["num_calls"] = str(len(assigned))
            row["channel_pattern"] = "-".join(c["channel"] for c in assigned)
            row["customer_id"] = assigned[0]["customer_id"] if assigned else ""
            row["story_hints"] = " || ".join(f"Call {c['call_index']}: {c['story_hint']}" for c in assigned if c.get("story_hint"))
            row["promo_codes_in_play"] = "|".join(dict.fromkeys(c["promotion_code"] for c in assigned if c.get("promotion_code")))
            row["promo_situation"] = next((c["promotion_time_status"] for c in assigned if c.get("promotion_time_status")), "none")
            row["policy_chunk_ids"] = "|".join(dict.fromkeys(x for c in assigned for x in c.get("policy_chunk_ids", "").split("|") if x))
            row["policy_situation"] = assigned[0].get("policy_case_type", "none") if assigned else "none"
            row["status"] = row.get("status", "todo")
    return rows


def read_call_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def validate_matrix(matrix_path: Path, *, outcome_floor: int = 10, include_all_levels: bool = False) -> list[str]:
    """Validate scenario/call contracts against the read-only BTC source data."""
    errors: list[str] = []
    scenarios = read_rows(matrix_path)
    calls_path = matrix_path.with_name("coverage_calls.csv")
    if not calls_path.exists():
        return [f"Missing call-level matrix: {calls_path}"]
    calls = read_call_rows(calls_path)
    with matrix_path.open(newline="", encoding="utf-8-sig") as stream:
        scenario_fields = set(csv.DictReader(stream).fieldnames or [])
    with calls_path.open(newline="", encoding="utf-8-sig") as stream:
        call_fields = set(csv.DictReader(stream).fieldnames or [])
    if scenario_fields != set(SCENARIO_COLUMNS):
        errors.append("Scenario matrix columns do not match the scenario-level schema")
    if call_fields != set(CALL_COLUMNS):
        errors.append("Call matrix columns do not match the call-level schema")
    known = {c["customer_id"]: c for c in load_json("catalog/crm_seed.json")["customers"]}
    products = {p["sku"]: p for p in load_json("catalog/products.json")["products"]}
    promo_by_code = {p["promo_code"]: p for p in load_json("catalog/promotions.json")["promotions"]}
    policy_ids = set(discovered_data()["policy_chunks"] + discovered_data()["old_policy_chunks"])
    old_policy_ids = set(discovered_data()["old_policy_chunks"])
    scenario_by_id = {s["slot_id"]: s for s in scenarios}
    if len({s["slot_id"] for s in scenarios}) != len(scenarios):
        errors.append("Scenario IDs must be unique")
    numbers = [int(s["case_number"]) for s in scenarios]
    if numbers and numbers != list(range(min(numbers), max(numbers) + 1)):
        errors.append("Scenario case_number values must be continuous")
    seen_m2 = False
    for scenario in scenarios:
        if scenario.get("level") == "M2":
            seen_m2 = True
        elif scenario.get("level") == "M1" and seen_m2:
            errors.append("All M1 scenarios must precede M2 scenarios")
        if scenario.get("level") == "M1" and scenario.get("nganh") != "thoi-trang":
            errors.append(f"{scenario['slot_id']}: M1 must stay in thoi-trang")
        milestone = load_dataset_config().get("milestones", {}).get(scenario.get("level", "M1"), {})
        if include_all_levels and scenario.get("level") in {"M1", "M2"}:
            if scenario.get("nganh") not in milestone.get("industries", []):
                errors.append(f"{scenario['slot_id']}: industry is outside {scenario.get('level')} configuration")
            if scenario.get("mien") not in milestone.get("regions", []) and scenario.get("special_customer") in {"", "none"}:
                errors.append(f"{scenario['slot_id']}: region is outside {scenario.get('level')} configuration")
    by_slot: dict[str, list[dict[str, str]]] = {}
    for call in calls:
        by_slot.setdefault(call["slot_id"], []).append(call)
        if call["customer_id"] not in known:
            errors.append(f"{call['slot_id']} call {call['call_index']}: unknown CRM customer {call['customer_id']}")
        elif call["customer_id"] in known and call["slot_id"] in scenario_by_id:
            customer = known[call["customer_id"]]
            if customer.get("region") != scenario_by_id[call["slot_id"]].get("mien") and scenario_by_id[call["slot_id"]].get("special_customer") in {"", "none"}:
                errors.append(f"{call['slot_id']} call {call['call_index']}: CRM region differs from scenario region")
        try:
            items = json.loads(call["products_json"])
        except (TypeError, json.JSONDecodeError):
            errors.append(f"{call['slot_id']} call {call['call_index']}: invalid products_json")
            continue
        for item in items:
            product = products.get(item.get("sku"))
            if not product:
                errors.append(f"{call['slot_id']} call {call['call_index']}: unknown SKU {item.get('sku')}")
            elif product.get("category", "").split("/", 1)[0] != next((s["nganh"] for s in scenarios if s["slot_id"] == call["slot_id"]), ""):
                errors.append(f"{call['slot_id']} call {call['call_index']}: SKU/category does not match scenario industry")
            elif (product.get("discontinued") or product.get("attributes", {}).get("discontinued") or item.get("sku", "").endswith("-OLD")) and call.get("expected_outcome") == "chot_don":
                errors.append(f"{call['slot_id']} call {call['call_index']}: discontinued SKU cannot be a closing item")
        for code in filter(None, call.get("promotion_code", "").split("|")):
            promo = promo_by_code.get(code)
            if not promo:
                errors.append(f"{call['slot_id']} call {call['call_index']}: unknown promotion {code}")
                continue
            applies = promo.get("applies_to", [])
            compatible = any("*" in applies or item.get("sku") in applies or any(
                target.startswith("category:") and products.get(item.get("sku"), {}).get("category", "").startswith(target.split(":", 1)[1])
                for target in applies
            ) for item in items)
            if not compatible:
                errors.append(f"{call['slot_id']} call {call['call_index']}: promotion {code} does not apply to assigned SKU/category")
            expected_time = promotion_time_status(code)
            if call.get("promotion_time_status") != expected_time:
                errors.append(f"{call['slot_id']} call {call['call_index']}: promotion {code} has time status {expected_time}, not {call.get('promotion_time_status')}")
            if code in {"AP-SEP", "11-11"} and scenario_by_id.get(call["slot_id"], {}).get("level") != "M2":
                errors.append(f"{call['slot_id']} call {call['call_index']}: {code} is reserved for M2 source context")
            if call.get("promotion_condition_focus") == "conditional_without_matching_promotion":
                errors.append(f"{call['slot_id']} call {call['call_index']}: conditional case lacks a compatible promotion")
        for chunk in filter(None, call.get("policy_chunk_ids", "").split("|")):
            if chunk not in policy_ids:
                errors.append(f"{call['slot_id']} call {call['call_index']}: unknown policy chunk {chunk}")
        if scenario_by_id.get(call["slot_id"], {}).get("hard_case_tag") == "version_conflict":
            if not call.get("order_date") or not set(filter(None, call.get("policy_chunk_ids", "").split("|"))) & old_policy_ids:
                errors.append(f"{call['slot_id']} call {call['call_index']}: old-policy case needs order_date and old-version chunks")
        if call.get("blocked_policy_sources") and call.get("policy_chunk_ids"):
            errors.append(f"{call['slot_id']} call {call['call_index']}: blocked policy source must not enter agent policy chunks")
        if not call.get("promotion_code") and call.get("promotion_time_status") != "none":
            errors.append(f"{call['slot_id']} call {call['call_index']}: promotion time status must be none without a promotion")
        if call["expected_outcome"] not in {"hen_goi_lai", "chot_don", "chuyen_may", "tu_choi"}:
            errors.append(f"{call['slot_id']} call {call['call_index']}: invalid outcome {call['expected_outcome']}")
    for scenario in scenarios:
        own = sorted(by_slot.get(scenario["slot_id"], []), key=lambda c: int(c["call_index"]))
        if len(own) < 1:
            errors.append(f"{scenario['slot_id']}: no calls")
        if [int(c["call_index"]) for c in own] != list(range(1, len(own) + 1)):
            errors.append(f"{scenario['slot_id']}: call_index must be continuous from 1")
        if scenario.get("hard_case_tag") == "shared_phone":
            ids = {c["customer_id"] for c in own}
            if len(own) < 2 or len(ids) < 2 or not any(known.get(cid, {}).get("shared_phone_with") in ids for cid in ids):
                errors.append(f"{scenario['slot_id']}: shared_phone needs two calls for linked CRM customers")
        if scenario.get("hard_case_tag") == "source_gap_product_exchange":
            if any(c.get("expected_outcome") != "tu_choi" or c.get("policy_chunk_ids") for c in own):
                errors.append(f"{scenario['slot_id']}: source-gap exchange must not assert an order action or unsupported policy")
        if scenario.get("hard_case_tag") == "product_exchange_refund_difference" and scenario.get("level") == "M2":
            for call in own:
                crm_orders = known.get(call["customer_id"], {}).get("orders", [])
                matching = next((o for o in crm_orders if o.get("order_id") == call.get("crm_order_id") and o.get("status") == "delivered" and o.get("sku") == call.get("existing_order_sku")), None)
                chunks = set(filter(None, call.get("policy_chunk_ids", "").split("|")))
                if not matching or not {"DT-03", "DT-04"}.issubset(chunks):
                    errors.append(f"{scenario['slot_id']} call {call['call_index']}: exchange needs a matching delivered CRM order and DT-03/DT-04 source")
    enabled = set(s.get("level", "M1") for s in scenarios) if include_all_levels else set(load_dataset_config().get("generation", {}).get("include_levels", ["M1"]))
    for level in dict.fromkeys(s.get("level", "M1") for s in scenarios if s.get("level", "M1") in enabled):
        counts = Counter(c["expected_outcome"] for c in calls if next((s["level"] for s in scenarios if s["slot_id"] == c["slot_id"]), "") == level)
        for outcome in ("hen_goi_lai", "chot_don", "chuyen_may", "tu_choi"):
            if counts[outcome] < outcome_floor:
                errors.append(f"{level}: {outcome} quota {counts[outcome]} < {outcome_floor}")
    return errors


def migrate_legacy_matrix(matrix_path: Path, briefs_dir: Path) -> tuple[int, int]:
    """Split a reviewed legacy matrix into scenario and per-call CSVs in place."""
    with matrix_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if "call_index" not in (reader.fieldnames or []) and set(SCENARIO_COLUMNS).issubset(set(reader.fieldnames or [])):
            raise ValueError("Matrix already uses the scenario-level schema; refusing to migrate it again")
        legacy = list(reader)
    scenarios: list[dict[str, str]] = []
    calls: list[dict[str, str]] = []
    for row in legacy:
        scenarios.append({key: row.get(key, "") for key in SCENARIO_COLUMNS})
        brief_path = briefs_dir / f"{row['slot_id']}.json"
        brief = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else None
        brief_calls = (brief or {}).get("calls", [])
        count = int(row.get("num_calls") or len(brief_calls) or 1)
        legacy_channels = row.get("channel_pattern", "hotline").split("-")
        promo_codes = [x for x in row.get("promo_codes_in_play", "").split("|") if x]
        policy_chunks = [x for x in row.get("policy_chunk_ids", "").split("|") if x]
        for index in range(1, count + 1):
            old = next((c for c in brief_calls if int(c.get("call_index", 0)) == index), {})
            customer_id = old.get("customer_id") or (brief or {}).get("customer_id") or row.get("customer_id", "")
            products = old.get("products", [])
            if not products:
                pool = _products_for_industry(row.get("nganh", ""))
                products = [{"sku": pool[(int(row.get("case_number", 1)) + index - 1) % len(pool)]["sku"], "qty": 1}] if pool else []
            promo_call = old.get("promo_codes_in_play", promo_codes)
            if isinstance(promo_call, list):
                promo_call = promo_call[0] if promo_call else ""
            outcome = old.get("expected_outcome")
            if outcome not in {"hen_goi_lai", "chot_don", "chuyen_may", "tu_choi"}:
                tag = row.get("hard_case_tag", "")
                outcome = "chuyen_may" if tag in {"three_channel_price_conflict", "inventory_runs_out_at_close", "price_pressure_internal_floor"} and index == count else "tu_choi" if tag in {"unanswerable", "restricted", "multi_product_cod_budget", "ai_identity_data_deletion"} else "hen_goi_lai" if index < count or tag in {"order_in_transit", "three_call_order_status", "callback_holiday"} else "chot_don"
            facts = old.get("facts_to_establish", {})
            calls.append({
                "slot_id": row["slot_id"], "call_index": str(index), "customer_id": customer_id,
                "channel": old.get("channel") or legacy_channels[min(index - 1, len(legacy_channels) - 1)],
                "products_json": json.dumps(products, ensure_ascii=False),
                "story_hint": old.get("story_hint") or story_hint_for_call(row.get("story_hints", ""), index),
                "expected_outcome": outcome, "promotion_code": promo_call or "",
                "promotion_time_status": promotion_time_status(promo_call) if promo_call else "none",
                "promotion_condition_focus": "variant_size_43" if row.get("hard_case_tag") == "size_excluded_promotion" else "eligibility_failure" if row.get("hard_case_tag") == "promo_condition_fail" else "none",
                "policy_chunk_ids": "|".join(old.get("policy_chunk_ids", policy_chunks) or []),
                "policy_case_type": row.get("policy_situation", "none"),
                "order_date": facts.get("purchase_date", ""),
                "crm_order_id": facts.get("existing_order_id", ""),
                "existing_order_sku": facts.get("existing_order_sku", ""),
                "blocked_policy_sources": "|".join(discovered_data()["blocked_policy_sources"]) if row.get("hard_case_tag") == "restricted" else "",
            })
    matrix_path.with_name("coverage_calls.csv").parent.mkdir(parents=True, exist_ok=True)
    with matrix_path.with_name("coverage_calls.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=CALL_COLUMNS); writer.writeheader(); writer.writerows(calls)
    with matrix_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=SCENARIO_COLUMNS); writer.writeheader(); writer.writerows(scenarios)
    return len(scenarios), len(calls)


def sync_regions(path: Path) -> int:
    """Set each matrix row's region from its assigned primary CRM customer."""
    customers = {c["customer_id"]: c for c in load_json("catalog/crm_seed.json")["customers"]}
    rows = read_rows(path)
    changed = 0
    for row in rows:
        customer = customers.get(row.get("customer_id", ""))
        if customer and customer.get("region") and row.get("mien") != customer["region"]:
            row["mien"] = customer["region"]
            changed += 1
    if changed:
        with path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows([{key: row.get(key, "") for key in SCENARIO_COLUMNS} for row in rows])
    print(f"Synchronized {changed} matrix region(s) from CRM -> {path}")
    return changed


def _report_level(rows: list[dict[str, str]], level: str, target: dict[str, Any], *, defer_audio: bool = False) -> bool:
    level_rows = [r for r in rows if r.get("level", "M1") == level]
    calls = sum(int(r["num_calls"]) for r in level_rows)
    multi_session_customers = {
        r.get("customer_id", "")
        for r in level_rows
        if int(r["num_calls"]) >= 2 and r.get("customer_id", "") not in {"", "TODO"}
    }
    multichannel_customers = {
        r.get("customer_id", "")
        for r in level_rows
        if r.get("customer_id", "") not in {"", "TODO"}
        and r["channel_pattern"].split("-")[0] != r["channel_pattern"].split("-")[-1]
    }
    audio_rows = [r for r in level_rows if r.get("audio_source")]
    audio_calls = sum(int(r["num_calls"]) for r in audio_rows)
    audio_hours = sum(float(r.get("audio_hours") or 0) for r in audio_rows)
    noisy = sum(str(r.get("audio_noisy", "no")).lower() in {"yes", "true", "1"} for r in audio_rows)
    ok = True

    def check(label: str, actual: float, minimum: float) -> None:
        nonlocal ok
        passed = actual >= minimum
        ok &= passed
        print(f"    [{'OK' if passed else 'MISSING'}] {label}: {actual:g} (need >= {minimum:g})")

    print(f"  {level}: {len(level_rows)} planned slots; briefed={sum(r.get('status') not in {'todo', 'source_gap'} for r in level_rows)}")
    check("transcripts", calls, target.get("transcripts_min", 0))
    check("multi-session customers", len(multi_session_customers), target.get("multi_session_customers_min", 0))
    check("multi-channel customers", len(multichannel_customers), target.get("multichannel_customers_min", 0))
    audio_target = target.get("audio", {})
    if defer_audio:
        print("    [DEFERRED] audio coverage (not in current generation phase)")
    else:
        check("audio transcripts", audio_calls, audio_target.get("transcripts_min", 0))
        check("audio hours", audio_hours, audio_target.get("hours_min", 0))
        check("noisy audio rows", noisy, target.get("noisy_audio_fraction_min", 0) * max(len(audio_rows), 1))
    return ok


def report(config: dict[str, Any], path: Path, dataset_config: dict[str, Any] | None = None, *, defer_audio: bool = False) -> None:
    rows = [r for r in read_rows(path) if r["status"] != "dropped"]
    quotas = config.get("quotas", {})
    ok = True

    print("Layers: A=hard-case/trap coverage; B=baseline diversity coverage")
    print(f"REF_DATE: {REF_DATE}")

    print("\nPlanning coverage targets (slot counts do not certify scenario content):")
    dataset_config = dataset_config or load_dataset_config()
    levels = dataset_config.get("generation", {}).get("include_levels") or dataset_config.get("ordering", {}).get("levels", ["M1"])
    for level in levels:
        ok = _report_level(rows, level, dataset_config.get("milestones", {}).get(level, {}), defer_audio=defer_audio) and ok

    def check(label: str, actual: int, minimum: int) -> None:
        nonlocal ok
        passed = actual >= minimum
        ok &= passed
        print(f"  [{'OK' if passed else 'MISSING'}] {label}: {actual} (need >= {minimum})")

    enabled_levels = set(
        dataset_config.get("generation", {}).get("include_levels")
        or dataset_config.get("ordering", {}).get("levels", ["M1"])
    )
    active_rows = [r for r in rows if r.get("level", "M1") in enabled_levels]
    calls_path = path.with_name("coverage_calls.csv")
    if calls_path.exists():
        plan_slots = {r["slot_id"] for r in rows}
        call_rows = [c for c in read_call_rows(calls_path) if c["slot_id"] in plan_slots]
        print("Outcome by call (level / layer / hard-case / outcome):")
        scenario_lookup = {r["slot_id"]: r for r in rows}
        groups: dict[tuple[str, str, str], Counter[str]] = {}
        for call in call_rows:
            scenario = scenario_lookup[call["slot_id"]]
            key = (scenario["level"], scenario["layer"], scenario.get("hard_case_tag", "") or "baseline")
            groups.setdefault(key, Counter())[call["expected_outcome"]] += 1
        for (level, layer, tag), outcome_counts in sorted(groups.items()):
            print(f"  {level}/{layer}/{tag}: " + ", ".join(f"{outcome}={outcome_counts[outcome]}" for outcome in ("chot_don", "hen_goi_lai", "chuyen_may", "tu_choi")))
        print("Outcome totals by level:")
        for level in sorted({r["level"] for r in rows}):
            counts = Counter(c["expected_outcome"] for c in call_rows if scenario_lookup[c["slot_id"]]["level"] == level)
            floor_status = "OK" if all(counts[outcome] >= int(config.get("quotas", {}).get("per_outcome_calls_min", 10)) for outcome in ("chot_don", "hen_goi_lai", "chuyen_may", "tu_choi")) else "MISSING"
            if level not in enabled_levels:
                floor_status = "DEFERRED" if floor_status != "OK" else "OK"
            print(f"  {level} [{floor_status}]: " + ", ".join(f"{outcome}={counts[outcome]}" for outcome in ("chot_don", "hen_goi_lai", "chuyen_may", "tu_choi")))
    print("Artifact states:")
    for status in ("todo", "briefed", "generated_dry_run", "generated_llm", "validated", "dropped"):
        count = sum(r.get("status", "todo") == status for r in active_rows)
        if count:
            print(f"  {status}: {count}")
    check("total calls", sum(int(r["num_calls"]) for r in active_rows), quotas.get("total_calls_min", 0))
    check(
        "multi-session customers",
        len({r["customer_id"] for r in active_rows if int(r["num_calls"]) >= 2 and r.get("customer_id")}),
        quotas.get("multi_session_min", 0),
    )
    check(
        "multi-channel customers",
        len({
            r["customer_id"] for r in active_rows
            if r.get("customer_id")
            and r["channel_pattern"].split("-")[0] != r["channel_pattern"].split("-")[-1]
        }),
        quotas.get("multichannel_min", 0),
    )

    for label, field, minimum in [
        ("persona",   "persona_id",   quotas.get("per_persona_min", 0)),
        ("category",  "nganh",        quotas.get("per_nganh_min", 0)),
        ("region",    "mien",         quotas.get("per_mien_min", 0)),
        ("hard case", "hard_case_tag", quotas.get("per_tag_min", 0)),
    ]:
        print(f"By {label}:")
        counts = Counter(r[field] for r in active_rows if r[field])
        for key, actual in sorted(counts.items()):
            check(key, actual, minimum)

    # Kiểm tra promo coverage
    print("By promo_situation:")
    promo_counts = Counter(r["promo_situation"] for r in active_rows)
    for sit in ["active", "expired", "not_started", "conditional", "none"]:
        print(f"  {sit}: {promo_counts.get(sit, 0)} slots")

    # Kiểm tra policy coverage
    print("By policy_situation:")
    policy_counts = Counter(r["policy_situation"] for r in active_rows)
    for sit in ["current", "old", "unanswerable", "restricted", "none"]:
        print(f"  {sit}: {policy_counts.get(sit, 0)} slots")

    print(f"\nRESULT: {'PLAN COVERAGE OK' if ok else 'PLAN COVERAGE INCOMPLETE - add slots'}")


def track(matrix: Path, briefs: Path, scenarios: Path, raw: Path, audio: Path | None, out: Path) -> None:
    """Refresh artifact status without changing the reviewed planning matrix."""
    rows = read_rows(matrix)
    for row in rows:
        if row["status"] in {"dropped", "source_gap"}:
            continue
        sid = row["slot_id"]
        brief_path = briefs / f"{sid}.json"
        scenario_path = scenarios / f"{sid}.json"
        raw_paths = [raw / f"{sid}_c{i}.json" for i in range(1, int(row["num_calls"]) + 1)]
        raw_complete = all(path.exists() for path in raw_paths)
        generation_modes: set[str] = set()
        brief_data = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else None
        if raw_complete and brief_data:
            from data_gen.gen_dialogue import generation_prompt
            expected_brief_digest = brief_digest(brief_data)
            scenario_num_calls = len(brief_data["calls"])
            expected_prompts = [generation_prompt(brief_data["persona_id"], call, scenario_num_calls)[1] for call in brief_data["calls"]]
        else:
            expected_brief_digest = None
            expected_prompts = []
        if raw_complete:
            for index, path in enumerate(raw_paths):
                try:
                    metadata = json.loads(path.read_text(encoding="utf-8")).get("generation_meta", {})
                except (OSError, json.JSONDecodeError):
                    raw_complete = False
                    break
                if metadata.get("dry_run") is True:
                    generation_modes.add("generated_dry_run")
                elif metadata.get("dry_run") is False:
                    generation_modes.add("generated_llm")
                else:
                    raw_complete = False
                    break
                if metadata.get("brief_digest") != expected_brief_digest or metadata.get("prompt_digest") != expected_prompts[index]:
                    raw_complete = False
                    break
        if len(generation_modes) > 1:
            raw_complete = False
        if brief_path.exists():
            brief = brief_data or {}
            customer_id = brief.get("customer_id", "")
            if customer_id and customer_id != "TODO":
                row["customer_id"] = customer_id
            channels = [call.get("channel", brief.get("channel", "")) for call in brief.get("calls", [])]
            if channels and all(channels):
                row["channel_pattern"] = "-".join(channels)
            if row.get("status") not in {"validated", "dropped"}:
                row["status"] = "briefed"
        if scenario_path.exists() and raw_complete:
            if len(generation_modes) == 1 and row.get("status") not in {"validated", "dropped"}:
                row["status"] = next(iter(generation_modes))
        elif row.get("status") == "validated":
            row["status"] = "briefed" if brief_path.exists() else "todo"
        # Optional per-scenario manifest: {"source":"tts", "hours":0.02, "noisy":true}
        audio_path = audio / f"{sid}.json" if audio else None
        if audio_path and audio_path.exists():
            metadata = json.loads(audio_path.read_text(encoding="utf-8"))
            row["audio_source"] = str(metadata.get("source", ""))
            row["audio_hours"] = str(metadata.get("hours", 0))
            row["audio_noisy"] = "yes" if metadata.get("noisy", False) else "no"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in SCENARIO_COLUMNS} for row in rows])
    print(f"Tracking refreshed: {out}")


def _products_for_industry(industry: str) -> list[dict[str, Any]]:
    products = load_json("catalog/products.json").get("products", [])
    matches = [
        product for product in products
        if product.get("category", "").split("/", 1)[0] == industry
        and not product.get("discontinued")
        and not product.get("attributes", {}).get("discontinued")
    ]
    return matches


def _teencode_level(case_number: int, *, hard_case: bool = False) -> str:
    """Stable 15/65/20 style distribution over ordinary chat scenarios."""
    if hard_case:
        return "heavy"
    bucket = (case_number - 1) % 20
    return "none" if bucket < 3 else "light" if bucket < 16 else "heavy"


def _brief_for_row(row: dict[str, str], customer: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a deterministic, reviewable brief from a coverage slot."""
    channels = row["channel_pattern"].split("-")
    persona_id = row["persona_id"]
    category = row["nganh"]
    tag = row.get("hard_case_tag", "")
    if tag == "three_channel_price_conflict":
        channels = ["hotline", "zalo_oa", "chat_fanpage"]
    product = products[int(row["case_number"]) % len(products)]
    selected_products = [product]
    selected_variant_id = None
    if tag == "multi_product_cod_budget":
        selected_products = sorted({p["sku"]: p for p in products}.values(), key=lambda p: p.get("list_price_vnd", 0), reverse=True)[:4]
        if len(selected_products) < 4 or sum(p.get("list_price_vnd", 0) for p in selected_products) <= 10_000_000:
            raise ValueError("multi_product_cod_budget requires four distinct catalog products totaling over the COD limit")
    if tag == "size_excluded_promotion":
        variant_parent = next((p for p in products if any(v.get("size") == 43 for v in p.get("variants", []))), None)
        if not variant_parent:
            raise ValueError("size_excluded_promotion requires a size-43 product variant")
        product = variant_parent
        selected_products = [product]
        selected_variant_id = next(v["variant_sku"] for v in product["variants"] if v.get("size") == 43)
        size_promo = next((p["promo_code"] for p in load_json("catalog/promotions.json")["promotions"] if 43 in p.get("conditions", {}).get("exclude_variant_size", [])), None)
        if not size_promo:
            raise ValueError("size_excluded_promotion requires a promotion excluding size 43")
    if tag == "inventory_runs_out_at_close":
        events = load_json("catalog/inventory_timeline.json").get("events", [])
        stock_skus = {event["sku"] for event in events}
        ref = REF_DATE.isoformat()
        later = (REF_DATE + timedelta(days=2)).isoformat()
        industry_skus = {p["sku"] for p in products} | {v["variant_sku"] for p in products for v in p.get("variants", [])}
        target_sku = None
        for candidate in sorted(stock_skus & industry_skus):
            current_events = sorted((e for e in events if e["sku"] == candidate and e["date"] <= ref), key=lambda e: e["date"])
            later_events = sorted((e for e in events if e["sku"] == candidate and e["date"] <= later), key=lambda e: e["date"])
            if current_events and later_events and current_events[-1]["qty"] > 0 and later_events[-1]["qty"] == 0:
                target_sku = candidate
                break
        stock_parent = next((p for p in products if p["sku"] == target_sku or any(v["variant_sku"] == target_sku for v in p.get("variants", []))), None)
        if not stock_parent:
            raise ValueError("inventory_runs_out_at_close requires a catalog item that stocks out between calls")
        product = stock_parent
        selected_products = [product]
        selected_variant_id = target_sku if target_sku != product["sku"] else None
    sku = product["sku"]
    promo_codes = [code for code in row.get("promo_codes_in_play", "").split("|") if code]
    policy_chunks = [chunk for chunk in row.get("policy_chunk_ids", "").split("|") if chunk]
    no_info = tag == "unanswerable"
    no_order = tag in {"multi_product_cod_budget", "ai_identity_data_deletion", "source_gap_product_exchange"}
    restricted = tag == "restricted"
    handoff = tag in {"three_channel_price_conflict", "inventory_runs_out_at_close", "price_pressure_internal_floor"}
    crm_customers = load_json("catalog/crm_seed.json")["customers"]
    shared_other = next((c for c in crm_customers if c.get("customer_id") == customer.get("shared_phone_with")), None) if tag == "shared_phone" else None
    shared_coat = next((p for p in products if p.get("sku") == "SKU-JK-DWN"), None) if tag == "shared_phone" else None
    shared_shoes = next((p for p in products if p.get("sku") == "SKU-SN-CAS"), None) if tag == "shared_phone" else None
    if tag == "shared_phone" and int(row["num_calls"]) >= 2 and (not shared_other or not shared_coat or not shared_shoes):
        raise ValueError("two-person shared_phone scenario requires both linked CRM records, SKU-WF-RO9 and SKU-SN-CAS")
    calls: list[dict[str, Any]] = []

    for index in range(1, int(row["num_calls"]) + 1):
        channel = channels[min(index - 1, len(channels) - 1)]
        call_customer = customer
        call_sku = sku
        call_products = selected_products
        call_variant_id = selected_variant_id
        if tag == "shared_phone" and int(row["num_calls"]) >= 2:
            # Call 1 is the linked CRM member with long-history context; call 2
            # is the matrix-assigned member with an independent product need.
            if index == 1:
                call_customer = shared_other
                call_sku = "SKU-JK-DWN"
                call_products = [shared_coat]
                call_variant_id = None
            else:
                call_customer = customer
                call_sku = "SKU-SN-CAS"
                call_products = [shared_shoes]
                call_variant_id = selected_variant_id
        identity_key = {"zalo_oa": "zalo_id", "chat_fanpage": "fb_id"}.get(channel, "phone")
        callback_at = None
        if tag == "three_call_order_status":
            outcome = "hen_goi_lai"
        elif no_info or restricted or no_order:
            outcome = "tu_choi"
        elif tag == "order_in_transit":
            outcome = "hen_goi_lai"
        elif index < int(row["num_calls"]):
            outcome = "hen_goi_lai"
        elif handoff:
            outcome = "chuyen_may"
        else:
            outcome = "chot_don"

        facts = {"product_advised": call_sku}
        if persona_id in {"khach_ngan_sach_hep", "khach_do_du_hoi_nguoi_nha"} or category.startswith("gia-dung"):
            product_price = next((p.get("list_price_vnd") for p in products if p.get("sku") == call_sku), 0)
            facts["budget_vnd"] = int(round(product_price * 1.2134 / 100_000) * 100_000)
        if tag == "shared_phone":
            facts["caller_identity"] = call_customer.get("name", "")
            facts["budget_vnd"] = 7000000 if call_customer.get("customer_id") == shared_other.get("customer_id") else 1500000
        if tag == "ttl_long_history":
            facts["customer_history_months"] = 8
        if tag == "three_channel_price_conflict":
            facts["prior_channel_quotes_differ"] = True
        if tag in {"size_excluded_promotion", "promo_condition_fail"}:
            facts["requested_variant_size"] = 43
        if tag == "version_conflict":
            facts["purchase_date"] = "2026-06-15"
        if tag == "product_exchange_refund_difference":
            delivered_order = next((o for o in customer.get("orders", []) if o.get("status") == "delivered"), None)
            if not delivered_order:
                raise ValueError(f"{row['slot_id']}: product exchange requires a delivered CRM order")
            facts["existing_order_id"] = delivered_order.get("order_id", "")
            facts["existing_order_sku"] = delivered_order.get("sku", "")
        if index == 1:
            facts["blocker"] = "can hoi con gai" if tag == "shared_phone" else "can hoi nguoi nha" if tag in {"teencode", "promo_condition_fail"} else "dang can nhac"
        elif tag == "ttl_long_history" and index > 1:
            address = crm_delivery_address(call_customer)
            if address:
                facts["address_confirmed"] = True
                facts["customer_address_to_confirm"] = address
        if tag in {"order_in_transit", "three_call_order_status"}:
            success_if = {"tool_called": "order.status"}
        elif tag == "product_exchange_refund_difference":
            success_if = {"tool_called": "order.update"}
        elif tag == "multi_product_cod_budget":
            success_if = {"tool_called": None, "must_not_call_tools": ["order.create"], "must_say_any": ["vượt ngân sách", "không phù hợp ngân sách"]}
        elif tag == "ai_identity_data_deletion":
            success_if = {"tool_called": None, "must_not_call_tools": ["order.create"], "must_say_any": ["AI", "trí tuệ nhân tạo"]}
        elif outcome == "chot_don":
            success_if: dict[str, Any] = {
                "tool_called": "order.create",
                "args_match": {"sku": call_sku, "qty": 1, "payment": "COD"},
            }
        elif outcome == "chuyen_may":
            success_if = {"tool_called": "handoff.transfer"}
        elif outcome == "hen_goi_lai":
            callback_at = "2026-10-26T09:00" if tag == "callback_holiday" else "2026-10-17T10:00"
            success_if = {"tool_called": "schedule.callback", "args_match": {"callback_at": callback_at}}
        else:
            success_if = {
                "tool_called": None,
                "must_not_call_tools": [
                    "crm.get_customer", "catalog.search", "inventory.check",
                    "order.create", "order.update", "order.status",
                    "schedule.callback", "handoff.transfer",
                ],
                "must_say_any": ["chưa có thông tin"] if no_info or tag == "source_gap_product_exchange" else ["không thể cung cấp"],
            }

        call_story = story_hint_for_call(row.get("story_hints", ""), index)
        if not call_story:
            raise ValueError(f"{row['slot_id']} call_{index}: coverage matrix story_hints is required")
        is_chat = channel in {"zalo_oa", "chat_fanpage"}
        level = _teencode_level(int(row["case_number"]), hard_case=tag == "teencode") if is_chat else "none"
        calls.append({
            "call_index": index,
            "days_later": 0 if index == 1 else 2,
            "channel": channel,
            "channel_identity": call_customer.get(identity_key),
            **({"customer_id": call_customer["customer_id"]} if tag == "shared_phone" and int(row["num_calls"]) >= 2 else {}),
            "products": [
                {"sku": item["sku"], "qty": 1, **({"variant_id": call_variant_id} if call_variant_id and item is call_products[0] else {})}
                for item in call_products
            ],
            "promo_codes_in_play": [size_promo] if tag == "size_excluded_promotion" else promo_codes,
            "policy_chunk_ids": policy_chunks,
            "facts_to_establish": {
                **facts,
                **({"callback_requested_at": "2026-10-26T09:00"} if tag == "callback_holiday" else {}),
                **({"sensitive_data_offer": "redacted_only"} if tag == "pii_cccd_bank_account" else {}),
                **({"budget_vnd": 8000000} if tag == "multi_product_cod_budget" else {}),
                **({"order_status_question": True} if tag == "three_call_order_status" else {}),
                **({"inventory_changes_between_calls": True} if tag == "inventory_runs_out_at_close" else {}),
            },
            "expected_outcome": outcome,
            "success_if": success_if,
            "story_hint": call_story,
            **({"must_carry_over": ["product_advised"], "must_not_ask": ["product_advised"]} if index > 1 and not (tag == "shared_phone" and int(row["num_calls"]) >= 2) else {}),
            "input_mode": "chat_teencode" if level != "none" else "clean",
            "teencode_level": level,
        })
        if outcome == "hen_goi_lai" and callback_at:
            calls[-1]["callback_at"] = callback_at

    return {
        "brief_id": row["slot_id"],
        "level": row.get("level", "M1"),
        "case_number": int(row["case_number"]),
        "persona_id": row["persona_id"],
        "customer_id": customer["customer_id"],
        "customer_name": customer.get("name"),
        "honorific": customer.get("honorific"),
        "channel": channels[0],
        "hard_case_tags": [tag] if tag else [],
        "calls": calls,
    }


def stubs(matrix: Path, out_dir: Path, *, overwrite: bool = False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    call_rows = read_call_rows(matrix.with_name("coverage_calls.csv")) if matrix.with_name("coverage_calls.csv").exists() else []
    calls_by_slot: dict[str, list[dict[str, str]]] = {}
    for call_row in call_rows:
        calls_by_slot.setdefault(call_row["slot_id"], []).append(call_row)
    for row in read_rows(matrix):
        if row["status"] == "dropped":
            continue
        path = out_dir / f"{row['slot_id']}.json"
        if path.exists() and not overwrite:
            continue
        crm_rows = load_json("catalog/crm_seed.json")["customers"]
        customer = next((c for c in crm_rows if c["customer_id"] == row.get("customer_id")), None)
        if customer is None:
            raise ValueError(f"{row['slot_id']}: assign a valid CRM customer_id before creating stubs")
        brief = _brief_for_row(row, customer, _products_for_industry(row["nganh"]))
        # The call-level CSV is authoritative. Replace all per-call fields in
        # the deterministic stub from it rather than re-deriving assignments.
        customer_by_id = {c["customer_id"]: c for c in crm_rows}
        for call in brief["calls"]:
            assigned = next((c for c in calls_by_slot.get(row["slot_id"], []) if int(c["call_index"]) == call["call_index"]), None)
            if not assigned:
                continue
            call_customer = customer_by_id[assigned["customer_id"]]
            channel = assigned["channel"]
            identity_field = {"zalo_oa": "zalo_id", "chat_fanpage": "fb_id"}.get(channel, "phone")
            call["customer_id"] = assigned["customer_id"]
            call["channel"] = channel
            call["channel_identity"] = call_customer.get(identity_field)
            call["products"] = json.loads(assigned["products_json"])
            call["story_hint"] = assigned["story_hint"]
            call["expected_outcome"] = assigned["expected_outcome"]
            if row.get("hard_case_tag") == "shared_phone":
                call.setdefault("facts_to_establish", {})["caller_identity"] = call_customer.get("name", "")
            call["promo_codes_in_play"] = [assigned["promotion_code"]] if assigned.get("promotion_code") else []
            call["policy_chunk_ids"] = [x for x in assigned.get("policy_chunk_ids", "").split("|") if x]
            if assigned.get("order_date"):
                call.setdefault("facts_to_establish", {})["purchase_date"] = assigned["order_date"]
            if assigned.get("crm_order_id"):
                call.setdefault("facts_to_establish", {})["existing_order_id"] = assigned["crm_order_id"]
                call["facts_to_establish"]["existing_order_sku"] = assigned.get("existing_order_sku", "")
            if row.get("hard_case_tag") == "product_exchange_refund_difference":
                call["success_if"] = {"tool_called": "order.update"}
                call.setdefault("facts_to_establish", {})["exchange_requested"] = True
            elif row.get("hard_case_tag") == "callback_holiday":
                callback_at = "2026-10-26T09:00"
                call["callback_at"] = callback_at
                call.setdefault("facts_to_establish", {})["callback_requested_at"] = callback_at
                call["expected_outcome"] = "hen_goi_lai"
                call["success_if"] = {"tool_called": "schedule.callback", "args_match": {"callback_at": callback_at}}
            elif assigned["expected_outcome"] == "chuyen_may":
                call["success_if"] = {"tool_called": "handoff.transfer"}
            elif assigned["expected_outcome"] == "chot_don":
                first_product = call["products"][0]
                call["success_if"] = {"tool_called": "order.create", "args_match": {"sku": first_product["sku"], "qty": first_product.get("qty", 1), "payment": "COD"}}
            elif assigned["expected_outcome"] == "hen_goi_lai" and call["success_if"].get("tool_called") != "order.status":
                call["success_if"] = {"tool_called": "schedule.callback"}
        if calls_by_slot.get(row["slot_id"]):
            brief["customer_id"] = calls_by_slot[row["slot_id"]][0]["customer_id"]
            brief["channel"] = calls_by_slot[row["slot_id"]][0]["channel"]
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        made += 1
    print(f"Generated {made} brief stubs in {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate", "report", "stubs", "track", "sync-regions", "sync-context", "validate", "migrate"])
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("matrix_config.json"))
    parser.add_argument("--matrix", type=Path, default=REPORTS_DIR / "coverage_matrix.csv")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--briefs", type=Path, default=BRIEFS_DIR)
    parser.add_argument("--scenarios", type=Path, default=DATA_GEN_DIR / "scenarios")
    parser.add_argument("--raw", type=Path, default=DATA_GEN_DIR / "raw")
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--defer-audio", action="store_true", help="Report non-audio coverage for a text-only generation phase")
    parser.add_argument("--all-levels", action="store_true", help="Validate outcome floors in M2 planning rows as well as enabled artifact levels")
    parser.add_argument("--force", action="store_true", help="Replace an existing matrix or regenerate briefs")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.command == "generate":
        generate(config, args.out or args.matrix, force=args.force)
    elif args.command == "report":
        report(config, args.matrix, defer_audio=args.defer_audio)
    elif args.command == "stubs":
        stubs(args.matrix, args.out or BRIEFS_DIR, overwrite=args.force)
    elif args.command == "track":
        track(args.matrix, args.briefs, args.scenarios, args.raw, args.audio, args.out or REPORTS_DIR / "coverage_tracking.csv")
    elif args.command == "sync-regions":
        sync_regions(args.matrix)
    elif args.command == "sync-context":
        count = synchronize_context_assignments(args.matrix, args.briefs)
        print(f"Synchronized promotion/policy assignments for {count} matrix row(s)")
    elif args.command == "migrate":
        scenario_count, call_count = migrate_legacy_matrix(args.matrix, args.briefs)
        print(f"Migrated {scenario_count} scenarios and {call_count} calls from reviewed matrix/briefs")
    else:
        errors = validate_matrix(args.matrix, outcome_floor=int(config.get("quotas", {}).get("per_outcome_calls_min", 10)), include_all_levels=args.all_levels)
        if errors:
            raise SystemExit("Matrix validation failed:\n- " + "\n- ".join(errors))
        print(f"Matrix validation passed: {len(read_rows(args.matrix))} scenarios, {len(read_call_rows(args.matrix.with_name('coverage_calls.csv')))} calls")


if __name__ == "__main__":
    main()
