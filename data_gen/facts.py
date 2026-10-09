from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .config import BTC_DIR, FACT_PACKS_DIR, REFERENCE_DATE


def load_mock_tools():
    path = BTC_DIR / "eval" / "mock_tools.py"
    spec = importlib.util.spec_from_file_location("btc_mock_tools_data_gen", path)
    if spec is None or spec.loader is None: raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def load(relative: str): return json.loads((BTC_DIR / relative).read_text(encoding="utf-8"))


def calls_by_index(brief: dict) -> dict[int, dict]:
    previous = date.fromisoformat(REFERENCE_DATE); result = {}
    for call in brief["calls"]:
        current = date.fromisoformat(call["call_date"]) if call.get("call_date") else previous + timedelta(days=call.get("days_later", 0))
        result[call["call_index"]] = {**call, "call_date": current.isoformat()}; previous = current
    return result


def extract_policy_chunks(chunk_ids: list[str]) -> list[dict[str, Any]]:
    result=[]
    for path in sorted((BTC_DIR / "policy").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for i, line in enumerate(lines):
            match = re.search(r"\[([A-Z0-9-]+)\]", line)
            if not match or match.group(1) not in chunk_ids: continue
            body=[]
            for next_line in lines[i + 1:]:
                if re.search(r"^##?\s+\[", next_line): break
                body.append(next_line)
            kind = "internal" if "NỘI BỘ" in text or "không cung cấp" in text.lower() else "old" if "HẾT HIỆU LỰC" in text else "current" if "2026-10" in text or "hiệu lực từ 01/10/2026" in text else "other"
            result.append({"chunk_id": match.group(1), "file": str(path.relative_to(BTC_DIR)), "type": kind, "text": "\n".join(body).strip(), "source": f"policy:{path.name}#{match.group(1)}"})
    return result


def build_fact_pack(brief: dict, call_index: int) -> dict[str, Any]:
    tools = load_mock_tools(); call = calls_by_index(brief)[call_index]
    crm = load("catalog/crm_seed.json")["customers"]
    customer = next((c for c in crm if c["customer_id"] == brief.get("customer_id")), None)
    customer_lookup = tools.crm_get_customer(phone=customer["phone"]) if customer else {"found": False, "customer_id": None}
    safe_crm = {
        k: v for k, v in customer_lookup.items()
        if k not in {"phone", "identities", "candidates", "orders", "sessions"}
    }
    if customer_lookup.get("orders"):
        safe_crm["orders"] = [{k: v for k, v in order.items() if k not in {"address", "customer_phone", "tracking"}} for order in customer_lookup["orders"]]
    if customer_lookup.get("sessions"):
        safe_crm["sessions"] = [{k: v for k, v in session.items() if k not in {"summary", "address", "phone"}} for session in customer_lookup["sessions"]]
    products = load("catalog/products.json")["products"]; by_sku = {p["sku"]: p for p in products}
    product_facts=[]
    for product in call.get("products", []):
        sku = product["variant_id"] if product.get("variant_id") else product["sku"]
        catalog_result = tools.catalog_search(sku=sku, include_discontinued=True)
        inventory = tools.inventory_check(sku=sku, on=call["call_date"])
        quote = tools.pricing_get_quote(sku=sku, on=call["call_date"], qty=product.get("qty", 1), customer_phone=(customer or {}).get("phone"), address=call.get("address"))
        product_facts.append({
            "requested_sku": product["sku"], "sku": sku, "variant_id": product.get("variant_id"), "qty": product.get("qty", 1),
            "catalog": catalog_result, "quote": quote, "inventory": inventory,
            "source": {"catalog": "eval.mock_tools.catalog_search + catalog/products.json", "quote": "eval.mock_tools.pricing_get_quote", "inventory": "eval.mock_tools.inventory_check"},
        })
    policies = extract_policy_chunks(call.get("policy_chunk_ids", []))
    safe_policy = [p for p in policies if p["type"] != "internal"]
    return {
        "brief_id": brief["brief_id"], "call_index": call_index, "call_date": call["call_date"],
        "reference_date": REFERENCE_DATE, "persona_id": brief["persona_id"], "channel": brief["channel"],
        "customer": {"customer_id": brief.get("customer_id"), "name": brief.get("customer_name"), "honorific": brief.get("honorific"), "crm": safe_crm},
        "customer_facts": call.get("facts_to_establish", {}), "products": product_facts,
        "policy": safe_policy, "internal_policy_ids": [p["chunk_id"] for p in policies if p["type"] == "internal"],
        "promo_codes_in_play": call.get("promo_codes_in_play", []),
        "sources": {"crm": "eval.mock_tools.crm_get_customer + catalog/crm_seed.json", "policy": "data/policy/*.md"},
    }


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--brief", required=True); ap.add_argument("--call", type=int, required=True); args=ap.parse_args()
    brief=json.loads(Path(args.brief).read_text(encoding="utf-8")); pack=build_fact_pack(brief, args.call)
    out=FACT_PACKS_DIR / f"{Path(args.brief).stem}_c{args.call}.json"; out.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(pack, ensure_ascii=False, indent=2)); print(f"wrote {out}")


if __name__ == "__main__": main()
