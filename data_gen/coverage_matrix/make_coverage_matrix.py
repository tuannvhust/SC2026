"""Generate and report a BTC-backed scenario coverage plan."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from data_gen.config import BRIEFS_DIR, BTC_DIR, REPORTS_DIR

COLUMNS = ["slot_id", "layer", "owner", "persona_id", "nganh", "mien", "num_calls", "channel_pattern", "hard_case_tag", "special_customer", "promo_situation", "policy_situation", "customer_id", "status", "notes"]
# A is the mandatory hard-case/trap layer; B is the baseline diversity layer.
LAYER_DESCRIPTIONS = {
    "A": "hard-case/trap coverage: required edge cases and policy/promotion/identity traps",
    "B": "baseline coverage: ordinary multi-call scenarios for broad persona/category/region diversity",
}
TRAPS = [("shared_phone", 2, "shared_phone", "none", "none"), ("ttl", 2, "long_history", "none", "none"), ("order_in_transit", 2, "order_in_transit", "none", "current"), ("version_conflict", 3, "none", "none", "old"), ("unanswerable", 3, "none", "none", "unanswerable"), ("restricted", 3, "none", "none", "restricted"), ("numeric", 3, "none", "conditional", "current"), ("multi_hop", 3, "none", "conditional", "current"), ("teencode", 3, "none", "active", "none"), ("promo_expired", 3, "none", "expired", "none"), ("promo_not_started", 2, "none", "not_started", "none"), ("promo_condition_fail", 2, "none", "conditional", "none")]
CHANNEL_PATTERNS = [("hotline", "hotline"), ("zalo_oa", "hotline"), ("chat_fanpage", "hotline"), ("zalo_oa", "hotline"), ("chat_fanpage", "zalo_oa")]
PROMO_SITUATIONS = ["active", "conditional", "none", "active"]
POLICY_SITUATIONS = ["current", "none", "current", "none", "current"]


def load(relative: str) -> Any:
    return json.loads((BTC_DIR / relative).read_text(encoding="utf-8"))


def discovered_data() -> dict[str, Any]:
    customers = load("catalog/crm_seed.json")["customers"]
    products = load("catalog/products.json")["products"]
    return {
        "personas": [p["persona_id"] for p in load("simulator/personas.json")["personas"]],
        "nganh": sorted({p["category"].split("/", 1)[0] for p in products}),
        "mien": ["bac", "trung", "nam"],
        "special_customers": {
            "shared_phone": next((c["customer_id"] for c in customers if c.get("shared_phone_with")), ""),
            "long_history": next((c["customer_id"] for c in customers if c.get("sessions")), ""),
            "order_in_transit": next((c["customer_id"] for c in customers if any(o.get("status") == "shipping" for o in c.get("orders", []))), ""),
        },
    }


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def generate(config: dict[str, Any], out: Path) -> None:
    data = discovered_data(); personas, nganh, mien = data["personas"], data["nganh"], data["mien"]; owners = config.get("owners", ["SV1", "SV2"]); rows = []
    def add(layer: str, tag: str, special: str, promo: str, policy: str, calls: int) -> None:
        i = len(rows); pattern = CHANNEL_PATTERNS[i % len(CHANNEL_PATTERNS)]
        rows.append({"slot_id": f"SC-{i + 1:03d}", "layer": layer, "owner": owners[i % len(owners)], "persona_id": personas[i % len(personas)], "nganh": nganh[(i + i // len(personas)) % len(nganh)], "mien": mien[(i + i // len(mien)) % len(mien)], "num_calls": calls, "channel_pattern": f"{pattern[0]}-{pattern[1]}", "hard_case_tag": tag, "special_customer": special, "promo_situation": promo, "policy_situation": policy, "customer_id": data["special_customers"].get(special, ""), "status": "todo", "notes": ""})
    for tag, count, special, promo, policy in TRAPS:
        for _ in range(count): add("A", tag, special, promo, policy, 2)
    for i in range(config.get("base_slots", 40)): add("B", "", "none", PROMO_SITUATIONS[i % len(PROMO_SITUATIONS)], POLICY_SITUATIONS[i % len(POLICY_SITUATIONS)], 3 if i % 3 == 2 else 2)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS); writer.writeheader(); writer.writerows(rows)
    print(f"Generated {len(rows)} slots -> {out} (personas={len(personas)}, categories={nganh}, regions={mien})")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f: return list(csv.DictReader(f))


def report(config: dict[str, Any], path: Path) -> None:
    rows = [r for r in read_rows(path) if r["status"] != "dropped"]; quotas = config.get("quotas", {}); ok = True
    print("Layers: A=hard-case/trap coverage; B=baseline diversity coverage")
    def check(label: str, actual: int, minimum: int) -> None:
        nonlocal ok; passed = actual >= minimum; ok &= passed; print(f"  [{'OK' if passed else 'MISSING'}] {label}: {actual} (need >= {minimum})")
    check("total calls", sum(int(r["num_calls"]) for r in rows), quotas.get("total_calls_min", 0)); check("multi-session scenarios", sum(int(r["num_calls"]) >= 2 for r in rows), quotas.get("multi_session_min", 0)); check("multi-channel scenarios", sum(r["channel_pattern"].split("-")[0] != r["channel_pattern"].split("-")[-1] for r in rows), quotas.get("multichannel_min", 0))
    for label, field, minimum in [("persona", "persona_id", quotas.get("per_persona_min", 0)), ("category", "nganh", quotas.get("per_nganh_min", 0)), ("region", "mien", quotas.get("per_mien_min", 0)), ("hard case", "hard_case_tag", quotas.get("per_tag_min", 0))]:
        print(f"By {label}:"); counts = Counter(r[field] for r in rows if r[field])
        for key, actual in sorted(counts.items()): check(key, actual, minimum)
    print(f"RESULT: {'COVERAGE OK' if ok else 'COVERAGE INCOMPLETE - add slots'}")


def stubs(matrix: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True); made = 0
    for row in read_rows(matrix):
        if row["status"] == "dropped": continue
        path = out_dir / f"{row['slot_id']}.json"
        if path.exists(): continue
        channel = row["channel_pattern"].split("-")[0]
        calls = [{"call_index": i, "days_later": 0 if i == 1 else None, "customer_goal": "TODO", "products": [{"sku": "TODO", "qty": 1}], "promo_codes_in_play": ["TODO"], "policy_chunk_ids": ["TODO"], "facts_to_establish": {}, "expected_outcome": "TODO", "story_hint": "TODO"} for i in range(1, int(row["num_calls"]) + 1)]
        brief = {"brief_id": row["slot_id"], "persona_id": row["persona_id"], "customer_id": row["customer_id"] or "TODO", "channel": channel, "hard_case_tags": [row["hard_case_tag"]] if row["hard_case_tag"] else [], "_matrix_hints": {"layer": row["layer"], "nganh": row["nganh"], "mien": row["mien"], "special_customer": row["special_customer"], "promo_situation": row["promo_situation"], "policy_situation": row["policy_situation"], "channel_pattern": row["channel_pattern"]}, "calls": calls}
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"); made += 1
    print(f"Generated {made} brief stubs in {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["generate", "report", "stubs"]); parser.add_argument("--config", type=Path, default=Path(__file__).with_name("matrix_config.json")); parser.add_argument("--matrix", type=Path, default=REPORTS_DIR / "coverage_matrix.csv"); parser.add_argument("--out", type=Path); args = parser.parse_args(); config = load_config(args.config)
    if args.command == "generate": generate(config, args.out or args.matrix)
    elif args.command == "report": report(config, args.matrix)
    else: stubs(args.matrix, args.out or BRIEFS_DIR)


if __name__ == "__main__": main()
