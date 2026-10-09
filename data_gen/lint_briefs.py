from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .config import BTC_DIR, BRIEFS_DIR, REPORTS_DIR


def btc_data() -> dict:
    def load(p): return json.loads((BTC_DIR / p).read_text(encoding="utf-8"))
    products = load("catalog/products.json")["products"]
    variants = {v["variant_sku"] for p in products for v in p.get("variants", [])}
    skus = {p["sku"] for p in products} | variants
    crm = load("catalog/crm_seed.json")["customers"]
    promos = {p["promo_code"] for p in load("catalog/promotions.json")["promotions"]}
    chunks = set()
    for path in (BTC_DIR / "policy").glob("*.md"):
        chunks.update(re.findall(r"\[([A-Z0-9-]+)\]", path.read_text(encoding="utf-8")))
    personas = {p["persona_id"] for p in load("simulator/personas.json")["personas"]}
    return {"skus": skus, "crm": {c["customer_id"] for c in crm}, "promos": promos, "chunks": chunks, "personas": personas}


def lint_one(path: Path, ref: dict) -> list[str]:
    errors = []
    try: brief = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc: return [f"invalid JSON: {exc}"]
    for key in ("brief_id", "persona_id", "customer_id", "channel", "calls"):
        if key not in brief: errors.append(f"missing {key}")
    if brief.get("persona_id") not in ref["personas"]: errors.append("invalid persona_id")
    customer = str(brief.get("customer_id", ""))
    if not (customer.startswith("NEW:") or customer in ref["crm"]): errors.append("invalid customer_id")
    indices = [c.get("call_index") for c in brief.get("calls", [])]
    if indices != list(range(1, len(indices) + 1)): errors.append("call_index must be continuous from 1")
    valid_outcomes = {"hen_goi_lai", "chot_don", "chuyen_may", "tu_choi"}
    for call in brief.get("calls", []):
        days_later = call.get("days_later", 0)
        if not isinstance(days_later, (int, float)) or isinstance(days_later, bool): errors.append(f"call {call.get('call_index')}: days_later must be numeric")
        elif days_later < 0: errors.append(f"call {call.get('call_index')}: days_later < 0")
        if call.get("expected_outcome") not in valid_outcomes: errors.append(f"call {call.get('call_index')}: invalid expected_outcome")
        products = call.get("products", [])
        if not isinstance(products, list): errors.append(f"call {call.get('call_index')}: products must be a list")
        for product in products if isinstance(products, list) else []:
            if not isinstance(product, dict): errors.append(f"call {call.get('call_index')}: product entry must be an object"); continue
            if product.get("sku") not in ref["skus"]: errors.append(f"call {call.get('call_index')}: invalid SKU")
            if product.get("variant_id") and product["variant_id"] not in ref["skus"]: errors.append(f"call {call.get('call_index')}: invalid variant_id")
        for promo in call.get("promo_codes_in_play", []):
            if promo not in ref["promos"]: errors.append(f"call {call.get('call_index')}: invalid promotion")
        for chunk in call.get("policy_chunk_ids", []):
            if chunk not in ref["chunks"]: errors.append(f"call {call.get('call_index')}: invalid policy chunk")
        for key in call.get("facts_to_establish", {}):
            if re.search(r"price_|promo_|discount|final_price|list_price", key, re.I): errors.append(f"call {call.get('call_index')}: forbidden factual key {key}")
        facts_text = json.dumps(call.get("facts_to_establish", {}), ensure_ascii=False)
        if re.search(r"(?<!\d)0\d{9}(?!\d)|\b0\d{11}\b|[\w.+-]+@[\w.-]+", facts_text): errors.append(f"call {call.get('call_index')}: unmasked PII in facts_to_establish")
    return errors


def main() -> None:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else BRIEFS_DIR
    ref = btc_data(); lines=[]; failed=False
    for path in sorted(directory.glob("*.json")):
        errors = lint_one(path, ref); failed |= bool(errors); lines.append(f"{path.name}: {'PASS' if not errors else 'FAIL'}")
        lines.extend(f"  - {e}" for e in errors)
    out = REPORTS_DIR / "lint_report.txt"; out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"), end="")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__": main()
