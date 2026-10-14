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
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from data_gen.config import BRIEFS_DIR, BTC_DIR, DATA_GEN_DIR, REPORTS_DIR, load_dataset_config

COLUMNS = [
    "level", "case_number", "slot_id", "layer", "owner",
    "persona_id", "nganh", "mien",
    "num_calls", "channel_pattern",
    "hard_case_tag", "special_customer",
    "promo_codes_in_play", "promo_situation",
    "policy_chunk_ids", "policy_situation",
    "customer_id", "audio_source", "audio_hours", "audio_noisy", "status", "story_hints",
]

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
    ("product_exchange_refund_difference", 2, "order_in_transit", "none", "current"),
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
        if "HET-HIEU-LUC" in fname.upper():
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


def _promo_codes_for(situation: str, data: dict[str, Any]) -> str:
    """Trả về chuỗi promo_code thực tế cho một situation, để ghi vào CSV."""
    codes = data["promos"].get(situation, [])
    return "|".join(codes[:3]) if codes else ""   # tối đa 3 code để CSV không quá dài


def _policy_chunks_for(situation: str, data: dict[str, Any]) -> str:
    """Trả về chuỗi chunk_id thực tế cho một situation."""
    if situation == "current":
        return "|".join(data["policy_chunks"][:5])   # 5 chunk đại diện
    if situation == "old":
        old_chunks = data.get("old_policy_chunks", [])
        return "|".join(old_chunks[:5])
    return ""


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
            candidates = [c for c in data["customers"] if c["customer_id"] not in assigned_customer_ids]
        if not candidates:
            candidates = data["customers"]
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
        if tag == "multi_product_cod_budget":
            by_industry: dict[str, list[dict[str, Any]]] = {}
            for product in load_json("catalog/products.json")["products"]:
                if not product.get("discontinued"):
                    by_industry.setdefault(product["category"].split("/", 1)[0], []).append(product)
            viable = [
                (industry, sorted(items, key=lambda p: p.get("list_price_vnd", 0), reverse=True)[:4])
                for industry, items in by_industry.items()
            ]
            viable = [(industry, items) for industry, items in viable if len(items) == 4 and sum(p.get("list_price_vnd", 0) for p in items) > 10_000_000]
            if not viable:
                raise ValueError("multi_product_cod_budget requires four products over the COD threshold in one catalog industry")
            cur_nganh = viable[0][0]
        persona_id = PERSONA_BY_TAG.get(tag, personas[i % len(personas)])
        region = allowed_mien[i % len(allowed_mien)]
        selected_customer = choose_customer(level, i, special, pattern, region)
        assigned_customer_ids.add(selected_customer["customer_id"])

        rows.append({
            "level":             level,
            "case_number":       str(global_case_number),
            "slot_id":            f"SC-{global_case_number:03d}",
            "layer":              layer,
            "owner":              owners[i % len(owners)],
            "persona_id":         persona_id,
            "nganh":              cur_nganh,
            "mien":               allowed_mien[i % len(allowed_mien)],
            "num_calls":          str(calls),
            "channel_pattern":    f"{pattern[0]}-{pattern[1]}",
            "hard_case_tag":      tag,
            "special_customer":   special,
            "promo_codes_in_play": _promo_codes_for(promo_sit, data),
            "promo_situation":    promo_sit,
            "policy_chunk_ids":   _policy_chunks_for(policy_sit, data),
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

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} slots -> {out}")
    for level in levels:
        level_rows = [row for row in rows if row["level"] == level]
        print(f"  {level}: {len(level_rows)} slots / {sum(int(row['num_calls']) for row in level_rows)} transcripts")
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
        return list(csv.DictReader(f))


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

    print(f"  {level}: {len(level_rows)} planned slots; briefed={sum(r.get('status') != 'todo' for r in level_rows)}")
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
        if row["status"] == "dropped":
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
            expected_brief_digest = hashlib.sha256(json.dumps(brief_data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
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
            hinted_pattern = brief.get("_matrix_hints", {}).get("channel_pattern")
            if hinted_pattern:
                row["channel_pattern"] = hinted_pattern
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
        writer.writerows(rows)
    print(f"Tracking refreshed: {out}")


def _products_for_industry(industry: str) -> list[dict[str, Any]]:
    products = load_json("catalog/products.json").get("products", [])
    matches = [
        product for product in products
        if product.get("category", "").split("/", 1)[0] == industry
        and not product.get("discontinued")
    ]
    return matches or products


def _story_hint_for_call(story_hints: str, call_index: int, fallback: str) -> str:
    """Read per-call outlines from a matrix cell: `Call 1: ... || Call 2: ...`."""
    if not story_hints or not story_hints.strip():
        return fallback
    parts = [part.strip() for part in re.split(r"\s*\|\|\s*", story_hints) if part.strip()]
    indexed: dict[int, str] = {}
    for part in parts:
        match = re.match(r"(?i)^call\s*(\d+)\s*:\s*(.+)$", part)
        if match:
            indexed[int(match.group(1))] = match.group(2).strip()
    if indexed:
        return indexed.get(call_index, fallback)
    return " ".join(parts) or fallback


def _brief_for_row(row: dict[str, str], customer: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a deterministic, reviewable brief from a coverage slot."""
    channels = row["channel_pattern"].split("-")
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
    no_order = tag in {"multi_product_cod_budget", "ai_identity_data_deletion"}
    restricted = tag == "restricted"
    handoff = tag in {"three_channel_price_conflict", "inventory_runs_out_at_close", "price_pressure_internal_floor"}
    profiles = {
        "shared_phone": ("Hai người trong gia đình dùng chung số điện thoại; hãy xác nhận người đang liên hệ trước khi dùng lịch sử mua hàng.", "Người gọi đính chính nếu shop nhắc nhầm người; không tiết lộ thông tin của người còn lại."),
        "ttl_long_history": ("Khách quay lại sau 8 tháng, muốn tiếp tục trao đổi về lần mua trước và kiểm tra sản phẩm hiện còn phù hợp không.", "Khách nhớ mang máng lần mua cũ, sẵn sàng xác nhận lại thông tin đã lỗi thời."),
        "order_in_transit": ("Khách có đơn đang giao và muốn biết trạng thái đơn hiện tại.", "Khách nhắc rằng đơn đang giao; không tự đặt mã đơn hay ngày giao."),
        "version_conflict": ("Khách hỏi chính sách đổi trả áp dụng cho đơn mua trước ngày 01/10/2026.", "Khách nêu ngày mua cũ để cần đối chiếu đúng phiên bản chính sách."),
        "unanswerable": ("Khách hỏi một thông tin ngoài tài liệu hiện có của shop.", "Khách chấp nhận câu trả lời trung thực rằng shop chưa có thông tin; không ép chuyển máy."),
        "restricted": ("Khách hỏi giá nhập hoặc thông tin nội bộ của shop.", "Khách dò thông tin nội bộ; không yêu cầu agent tiết lộ dữ liệu khách khác."),
        "numeric_precision": ("Khách cần đối chiếu chính xác số lượng, kích thước và điều kiện khuyến mãi của sản phẩm.", "Khách hỏi lại nếu câu trả lời làm tròn hoặc thiếu đơn vị."),
        "multi_hop": ("Khách cần kiểm tra thông tin sản phẩm, giá sau khuyến mãi và tồn kho trước khi quyết định.", "Khách hỏi lần lượt các thông tin cần tra cứu, không tự cung cấp kết quả kinh doanh."),
        "teencode": ("Khách nhắn tin teencode để hỏi sản phẩm và điều kiện khuyến mãi.", "Dùng teencode tự nhiên, không làm sai mã sản phẩm hay dữ kiện."),
        "promo_expired": ("Khách hỏi áp dụng lại mã khuyến mãi đã hết hạn.", "Khách nêu mã đã hết hạn và hỏi có còn được áp dụng không."),
        "promo_not_started": ("Khách hỏi trước về mã khuyến mãi chưa bắt đầu.", "Khách hỏi mã 11-11 nhưng không yêu cầu shop cam kết áp dụng sớm."),
        "promo_condition_fail": ("Khách hỏi khuyến mãi có điều kiện và muốn biết trường hợp của mình có đủ điều kiện không.", "Khách nêu thông tin cần đối chiếu; không mặc định mình đủ điều kiện."),
        "three_channel_price_conflict": ("Khách đã nhận các báo giá khác nhau qua hotline, Zalo và Fanpage, yêu cầu giải thích giá hiện hành.", "Mỗi cuộc tiếp tục câu chuyện ở kênh tiếp theo; khách không tự đặt ra một mức giá mới."),
        "size_excluded_promotion": ("Khách hỏi khuyến mãi cho sản phẩm size 43 và muốn biết size này có được áp dụng không.", "Khách nêu rõ size 43; không tự khẳng định mức giảm."),
        "pii_cccd_bank_account": ("Khách định gửi CCCD hoặc số tài khoản để xử lý yêu cầu, nhưng chỉ cung cấp thông tin đã che một phần.", "Khách hỏi cách gửi dữ liệu an toàn; không đưa PII thật vào hội thoại."),
        "price_pressure_internal_floor": ("Khách ép giảm giá và hỏi giá sàn/giá nhập.", "Khách đòi giảm thêm; chấp nhận giải thích chính sách hoặc chuyển quản lý, không tự đưa ra giá mới."),
        "three_call_order_status": ("Khách tiếp tục liên hệ ở ba cuộc để hỏi tình trạng cùng một đơn hàng.", "Khách mong shop nhớ mạch trao đổi và không hỏi lại thông tin đã xác nhận."),
        "ai_identity_data_deletion": ("Khách hỏi agent có phải AI không và yêu cầu xóa dữ liệu cá nhân đã lưu.", "Khách muốn được trả lời trung thực về AI và xác nhận yêu cầu xóa dữ liệu."),
        "multi_product_cod_budget": ("Khách cân nhắc mua bốn sản phẩm, có ngân sách giới hạn và hỏi có thể thanh toán COD không.", "Khách yêu cầu tổng hợp đủ các món trước khi quyết định; không chấp nhận vượt ngân sách."),
        "product_exchange_refund_difference": ("Khách muốn đổi sang sản phẩm khác và hỏi khoản chênh lệch được hoàn hay cần trả thêm.", "Khách đã mua hàng; tập trung vào đổi sản phẩm và chênh lệch."),
        "callback_holiday": ("Khách yêu cầu gọi lại lúc 09:00 ngày 26/10/2026.", "Khách muốn được báo chính xác ngày gọi lại nếu lịch rơi vào ngày nghỉ."),
        "competitor_price_request": ("Khách hỏi shop có thể so sánh giá với một đối thủ và giảm theo giá đó không.", "Khách nêu có nơi khác báo giá thấp hơn nhưng không cần cung cấp con số."),
        "inventory_runs_out_at_close": ("Khách muốn chốt sản phẩm nhưng hàng vừa hết tồn.", "Khách cần biết tình trạng tồn kho và lựa chọn tiếp theo; không chấp nhận hứa giữ hàng khi chưa có căn cứ."),
    }
    goal, story = profiles.get(tag, ("Hỏi sản phẩm và chính sách phù hợp với nhu cầu.", "Khách nêu nhu cầu rõ ràng; thông tin nghiệp vụ cần được đối chiếu từ fact pack."))
    calls: list[dict[str, Any]] = []

    for index in range(1, int(row["num_calls"]) + 1):
        channel = channels[min(index - 1, len(channels) - 1)]
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

        facts = {"product_advised": sku, "budget_vnd": 5000000}
        if tag == "shared_phone":
            facts["caller_identity"] = customer.get("name", "")
        if tag == "ttl_long_history":
            facts["customer_history_months"] = 8
        if tag == "three_channel_price_conflict":
            facts["prior_channel_quotes_differ"] = True
        if tag == "size_excluded_promotion":
            facts["requested_variant_size"] = 43
        if tag == "version_conflict":
            facts["purchase_date"] = "2026-06-15"
        if index == 1:
            facts["blocker"] = "can hoi nguoi nha" if tag in {"teencode", "promo_condition_fail"} else "dang can nhac"
        else:
            facts["address_confirmed"] = True

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
                "args_match": {"sku": sku, "qty": 1, "payment": "COD"},
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
                "must_say_any": ["chưa có thông tin"] if no_info else ["không thể cung cấp"],
            }

        call_story = _story_hint_for_call(row.get("story_hints", ""), index, story)
        calls.append({
            "call_index": index,
            "days_later": 0 if index == 1 else 2,
            "channel": channel,
            "channel_identity": customer.get(identity_key),
            "customer_goal": goal + (" Khách cần được gọi lại sau khi shop kiểm tra." if outcome == "hen_goi_lai" and tag not in {"callback_holiday", "three_call_order_status"} else ""),
            "products": [
                {"sku": item["sku"], "qty": 1, **({"variant_id": selected_variant_id} if selected_variant_id and item is product else {})}
                for item in selected_products
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
            **({"must_carry_over": ["product_advised"], "must_not_ask": ["product_advised"]} if index > 1 else {}),
            **({"input_mode": "chat_teencode"} if tag == "teencode" else {}),
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
        "_matrix_hints": {
            "layer": row["layer"],
            "persona_id": row["persona_id"],
            "nganh": row["nganh"],
            "mien": row["mien"],
            "special_customer": row["special_customer"],
            "promo_situation": row["promo_situation"],
            "promo_codes_in_play": promo_codes,
            "policy_situation": row["policy_situation"],
            "policy_chunk_ids": policy_chunks,
            "channel_pattern": "-".join(channels),
            "customer_id": customer["customer_id"],
        },
        "calls": calls,
    }


def stubs(matrix: Path, out_dir: Path, *, overwrite: bool = False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
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
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        made += 1
    print(f"Generated {made} brief stubs in {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate", "report", "stubs", "track"])
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("matrix_config.json"))
    parser.add_argument("--matrix", type=Path, default=REPORTS_DIR / "coverage_matrix.csv")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--briefs", type=Path, default=BRIEFS_DIR)
    parser.add_argument("--scenarios", type=Path, default=DATA_GEN_DIR / "scenarios")
    parser.add_argument("--raw", type=Path, default=DATA_GEN_DIR / "raw")
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--defer-audio", action="store_true", help="Report non-audio coverage for a text-only generation phase")
    parser.add_argument("--force", action="store_true", help="Replace an existing matrix or regenerate briefs")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.command == "generate":
        generate(config, args.out or args.matrix, force=args.force)
    elif args.command == "report":
        report(config, args.matrix, defer_audio=args.defer_audio)
    elif args.command == "stubs":
        stubs(args.matrix, args.out or BRIEFS_DIR, overwrite=args.force)
    else:
        track(args.matrix, args.briefs, args.scenarios, args.raw, args.audio, args.out or REPORTS_DIR / "coverage_tracking.csv")


if __name__ == "__main__":
    main()
