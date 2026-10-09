from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

from .config import BTC_DIR, REPORTS_DIR


def load_json(relative: str):
    return json.loads((BTC_DIR / relative).read_text(encoding="utf-8"))


def policy_inventory() -> list[dict]:
    rows = []
    for path in sorted((BTC_DIR / "policy").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        kind = "internal" if "NỘI BỘ" in text or "không cung cấp" in text.lower() else "old" if "HẾT HIỆU LỰC" in text else "current" if "2026-10" in text or "hiệu lực từ 01/10/2026" in text else "other"
        chunks = [line.split("]", 1)[0] + "]" for line in text.splitlines() if line.startswith("[") or line.startswith("## [")]
        rows.append({"file": path.name, "type": kind, "chunk_count": len(chunks), "chunk_ids": ";".join(chunks)})
    return rows


def main() -> None:
    crm = load_json("catalog/crm_seed.json")["customers"]
    promos_doc = load_json("catalog/promotions.json")
    ref = date.fromisoformat(promos_doc["reference_date"])
    promo_rows = []
    for promo in promos_doc["promotions"]:
        state = "not_started" if ref < date.fromisoformat(promo["start"]) else "expired" if ref > date.fromisoformat(promo["end"]) else "active"
        promo_rows.append({"file": "catalog/promotions.json", "type": "promotion", "chunk_count": 1, "chunk_ids": f"{promo['promo_code']}:{state}"})
    shared = {phone for phone, rows in __import__("itertools").groupby(sorted(crm, key=lambda x: x["phone"]), key=lambda x: x["phone"]) if len(list(rows)) > 1}
    special = [{"file": "catalog/crm_seed.json", "type": "customer_special", "chunk_count": 1, "chunk_ids": c["customer_id"] + (":shared_phone" if c["phone"] in shared else "") + (":orders" if c.get("orders") else "") + (":sessions" if c.get("sessions") else "")} for c in crm if c["phone"] in shared or c.get("orders") or c.get("sessions")]
    personas = load_json("simulator/personas.json")["personas"]
    persona_rows = [{"file": "simulator/personas.json", "type": "persona", "chunk_count": 1, "chunk_ids": p["persona_id"] + ":" + p["style"]} for p in personas]
    rows = policy_inventory() + promo_rows + special + persona_rows
    out = REPORTS_DIR / "data_inventory.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "type", "chunk_count", "chunk_ids"])
        writer.writeheader(); writer.writerows(rows)
    print(f"BTC_DIR={BTC_DIR}")
    print(f"customers={len(crm)} shared_phone_customers={sum(c['phone'] in shared for c in crm)}")
    print(f"promotions={len(promo_rows)} states={dict(Counter(x['chunk_ids'].rsplit(':', 1)[-1] for x in promo_rows))}")
    print(f"personas={len(personas)} policies={len(policy_inventory())} -> {out}")


if __name__ == "__main__": main()
