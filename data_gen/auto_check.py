from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
from pathlib import Path

from .config import BRIEFS_DIR, BTC_DIR, FACT_PACKS_DIR, RAW_DIR, REPORTS_DIR, SCENARIOS_DIR


def mock_tools():
    path=BTC_DIR / "eval/mock_tools.py"; spec=importlib.util.spec_from_file_location("btc_mock_tools_autocheck", path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def words(text: str) -> list[str]: return re.findall(r"[\wÀ-ỹ]+", text.lower())


def money_values(text: str) -> set[int]:
    values=set()
    for m in re.finditer(r"(?<!\d)(\d{1,3}(?:[.]\d{3})+|\d+(?:[,.]\d+)?)\s*(triệu|tr|k|đ|vnd)?", text.lower()):
        raw, unit=m.group(1), m.group(2); raw=raw.replace(".", "").replace(",", ".") if "." in raw or "," in raw else raw
        try: value=float(raw)
        except ValueError: continue
        if unit in {"triệu","tr"}: value*=1_000_000
        elif unit == "k": value*=1_000
        values.add(int(value))
    return values


def row(sid, call, code, description, excerpt, hard=True): return {"scenario_id":sid,"call_index":call,"error_code":code,"description":description,"excerpt":excerpt,"hard":hard}


def check_one(path: Path, briefs_dir: Path, packs_dir: Path) -> list[dict]:
    scenario=json.loads(path.read_text(encoding="utf-8")); sid=scenario["scenario_id"]; rows=[]
    brief=json.loads((briefs_dir / f"{sid}.json").read_text(encoding="utf-8")) if (briefs_dir / f"{sid}.json").exists() else None
    crm=json.loads((BTC_DIR / "catalog/crm_seed.json").read_text(encoding="utf-8"))["customers"]
    customer=next((c for c in crm if brief and c["customer_id"] == brief.get("customer_id")), None)
    internal_text=" ".join(p.read_text(encoding="utf-8") for p in (BTC_DIR / "policy").glob("*.md") if "NỘI BỘ" in p.read_text(encoding="utf-8") or "không cung cấp" in p.read_text(encoding="utf-8")).lower()
    for name, call in scenario.get("calls", {}).items():
        index=int(name.split("_")[-1]); raw_path=RAW_DIR / f"{sid}_c{index}.json"; raw=json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else {"dialogue":[]}
        agent=" ".join(x["text"] for x in raw.get("dialogue", []) if x.get("role")=="agent")
        pack_path=packs_dir / f"{sid}_c{index}.json"; pack=json.loads(pack_path.read_text(encoding="utf-8")) if pack_path.exists() else None
        if not pack: rows.append(row(sid,index,"E2_MISSING_FACT_PACK","fact pack missing",str(pack_path))); continue
        valid_numbers=set();
        for product in pack.get("products", []):
            quote=product.get("quote", {}); valid_numbers |= {v for v in [quote.get("list_price_vnd"), quote.get("final_price_vnd")] if isinstance(v,int)}
            valid_numbers |= {p.get("discount_vnd") for p in quote.get("applied_promos",[]) if isinstance(p.get("discount_vnd"),int)}
        valid_numbers |= {v for v in pack.get("customer_facts", {}).values() if isinstance(v, int)}
        bad=money_values(agent) - valid_numbers
        if bad: rows.append(row(sid,index,"E3_WRONG_NUMERIC","agent numeric values not in fact/customer values",str(sorted(bad))))
        if re.search(r"(?<!\d)0\d{9}(?!\d)|\b0\d{11}\b|[\w.+-]+@[\w.-]+", agent): rows.append(row(sid,index,"E6_PII","unmasked phone/CCCD/email in agent dialogue",agent))
        internal_words=words(internal_text); spoken=words(agent); leaked=[]
        for start in range(max(0,len(spoken)-5)):
            if len(spoken[start:start+6]) == 6 and " ".join(spoken[start:start+6]) in " ".join(internal_words): leaked.append(" ".join(spoken[start:start+6]))
        if leaked: rows.append(row(sid,index,"E6_INTERNAL_POLICY","six-word internal policy sequence leaked",leaked[0]))
        keywords=json.loads((Path(__file__).parent / "slot_keywords.json").read_text(encoding="utf-8")); known=set(call.get("must_not_ask", []))
        for slot in known:
            if any(k in agent.lower() for k in keywords.get(slot, [])) and "?" in agent and not re.search(r"đúng không|vẫn là", agent.lower()):
                rows.append(row(sid,index,"E8_REASK_REVIEW","possible open question for known slot",slot,False))
        tool=mock_tools(); product=(pack.get("products") or [{}])[0]; sku=product.get("sku")
        if sku in getattr(tool,"_BY_SKU",{}):
            quote=tool.pricing_get_quote(sku=sku,on=pack["call_date"],customer_phone=(customer or {}).get("phone")); inv=tool.inventory_check(sku=sku,on=pack["call_date"]); gt=call.get("ground_truth_facts", {})
            if gt.get("price_vnd") != quote.get("final_price_vnd") or gt.get("in_stock") != inv.get("in_stock"):
                expected={"price_vnd":quote.get("final_price_vnd"),"in_stock":inv.get("in_stock")}
                rows.append(row(sid,index,"E2_FACT_MISMATCH","scenario ground truth differs from direct mock_tools",json.dumps({"scenario":gt,"expected":expected},ensure_ascii=False)))
    return rows


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--scenarios", default=str(SCENARIOS_DIR)); ap.add_argument("--briefs", default=str(BRIEFS_DIR)); ap.add_argument("--fact-packs", default=str(FACT_PACKS_DIR)); args=ap.parse_args()
    rows=[]
    for path in sorted(Path(args.scenarios).glob("*.json")): rows.extend(check_one(path,Path(args.briefs),Path(args.fact_packs)))
    validator=BTC_DIR / "eval/validate_scenarios.py"
    if not validator.exists(): rows.append(row("*","*","BTC_VALIDATOR_MISSING","BTC validator is absent from checkout",str(validator),False))
    out=REPORTS_DIR / "auto_check_report.csv"
    with out.open("w",newline="",encoding="utf-8") as f:
        fields=["scenario_id","call_index","error_code","description","excerpt","hard"]; writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    counts={}
    for r in rows: counts[r["error_code"]]=counts.get(r["error_code"],0)+1
    print(json.dumps(counts,ensure_ascii=False)); print(out)
    raise SystemExit(1 if any(r["hard"] for r in rows) else 0)


if __name__ == "__main__": main()
