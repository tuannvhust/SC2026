from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import BTC_DIR, DRYRUN_DIR, FACT_PACKS_DIR, RAW_DIR, SCENARIOS_DIR
from .facts import build_fact_pack


def crm_record(brief: dict) -> dict:
    customers = json.loads((BTC_DIR / "catalog/crm_seed.json").read_text(encoding="utf-8"))["customers"]
    return next((c for c in customers if c["customer_id"] == brief.get("customer_id")), {
        "customer_id": brief.get("customer_id"), "name": "Khách hàng", "honorific": "anh/chị", "phone": "<NEW>"
    })


def derive_success_if(call: dict, pack: dict) -> dict:
    if call.get("success_if"):
        condition = dict(call["success_if"])
    else:
        outcome = call["expected_outcome"]
        product = (pack.get("products") or [{}])[0]
        quote = product.get("quote", {})
        if outcome == "chot_don":
            args = {"sku": product.get("sku"), "price_vnd": quote.get("final_price_vnd"), "qty": product.get("qty", 1)}
            if call.get("payment"):
                args["payment"] = call["payment"]
            condition = {"tool_called": "order.create", "args_match": args}
        elif outcome == "hen_goi_lai":
            condition = {"tool_called": "schedule.callback"}
        elif outcome == "chuyen_may":
            condition = {"tool_called": "handoff.transfer"}
        else:
            condition = {"tool_called": None, "must_not_call_tools": []}
            if call.get("no_information") or call.get("hard_case") == "unanswerable":
                condition["must_say_any"] = ["không có thông tin", "chưa có thông tin"]
                condition["must_not_call_tools"] = [
                    "crm.get_customer", "catalog.search", "inventory.check", "order.create",
                    "order.update", "order.status", "schedule.callback", "handoff.transfer",
                ]
    for field in ("also_ordered", "total_match_vnd", "brief_must_contain", "must_say_any", "agent_must_say", "must_not_call_tools", "forbidden_claims", "trace_must_not_match", "max_agent_questions"):
        if field in call:
            condition[field] = call[field]
    return condition


def derive_ground_truth(pack: dict) -> dict:
    products = pack.get("products") or [{}]
    product = products[0]
    quote = product.get("quote", {})
    inventory = product.get("inventory", {})
    result = {
        "price_vnd": quote.get("final_price_vnd"),
        "list_price_vnd": quote.get("list_price_vnd"),
        "in_stock": inventory.get("in_stock"),
    }
    if inventory.get("restock_expected") is not None:
        result["restock_date"] = inventory["restock_expected"]
    if "freeship" in quote:
        result["freeship"] = quote["freeship"]
    for promo in quote.get("applied_promos", []):
        result[f"promo_{promo['promo_code']}_active"] = True
    for promo in quote.get("expired_promos", []):
        result[f"promo_{promo}_active"] = False
    for index, item in enumerate(products, start=1):
        result[f"product_{index}_sku"] = item.get("sku")
        result[f"product_{index}_qty"] = item.get("qty", 1)
        result[f"product_{index}_price_vnd"] = item.get("quote", {}).get("final_price_vnd")
        result[f"product_{index}_in_stock"] = item.get("inventory", {}).get("in_stock")
    return result


def assemble_scenario(brief: dict, raw_by_call: dict[int, dict], packs_by_call: dict[int, dict]) -> dict:
    """Convert reviewed brief + deterministic facts + customer-only turns into evaluator input."""
    customer = crm_record(brief)
    previous_facts: dict = {}
    calls = {}
    for call_index in sorted(c["call_index"] for c in brief["calls"]):
        spec = next(c for c in brief["calls"] if c["call_index"] == call_index)
        pack = packs_by_call[call_index]
        raw = raw_by_call[call_index]
        turns = raw.get("customer_turns")
        if turns is None:  # accept legacy review data, but newly generated data is customer-only
            turns = [item["text"] for item in raw.get("dialogue", []) if item.get("role") == "customer"]

        known = set(previous_facts) | {"customer_id", "customer_name", "honorific"}
        must_not_ask = sorted(known & {
            "room_area_m2", "budget_vnd", "product_advised", "price_quoted_vnd",
            "blocker", "address_confirmed", "order_id",
        })
        carry = sorted(set(previous_facts) & {
            "product_advised", "price_quoted_vnd", "room_area_m2", "budget_vnd",
            "blocker", "competitor_context", "old_promotion_mentioned",
        })
        channel = spec.get("channel", brief.get("channel", "hotline"))
        identity_field = {"zalo_oa": "zalo_id", "chat_fanpage": "fb_id"}.get(channel)
        identity = spec.get("channel_identity") or (customer.get(identity_field) if identity_field else customer.get("phone"))
        call_out = {
            "call_date": pack["call_date"], "channel": channel, "channel_identity": identity,
            "customer_goal": spec["customer_goal"], "customer_turns": turns,
            "facts_established": spec.get("facts_to_establish", {}),
            "must_carry_over": spec.get("must_carry_over", carry),
            "must_not_ask": spec.get("must_not_ask", must_not_ask),
            "success_if": derive_success_if(spec, pack),
            "ground_truth_facts": derive_ground_truth(pack),
            "expected_outcome": spec["expected_outcome"],
        }
        for field in (
            "input_mode", "customer_turns_asr", "seed_history", "memory_expectation",
            "forbidden_claims", "trace_must_not_match", "brief_must_contain",
            "agent_must_say", "max_agent_questions",
        ):
            if field in spec:
                call_out[field] = spec[field]
        calls[f"call_{call_index}"] = call_out
        previous_facts.update(spec.get("facts_to_establish", {}))
        for item in pack.get("products", []):
            previous_facts["product_advised"] = item.get("sku")
            previous_facts["price_quoted_vnd"] = item.get("quote", {}).get("final_price_vnd")

    scenario = {
        "scenario_id": brief["brief_id"], "customer_id": brief.get("customer_id"),
        "level": brief.get("level", "M1"), "persona": brief["persona_id"],
        "hard_case": "_".join(brief.get("hard_case_tags", [])) or None,
        "customer_phone": customer.get("phone"), "customer_name": customer.get("name"),
        "honorific": customer.get("honorific"),
        "notes": "Generated from reviewed brief; raw generation contains customer turns only.",
        "calls": calls,
    }
    if brief.get("case_number") is not None:
        scenario["case_number"] = brief["case_number"]
    return scenario


def validate_scenario(scenario: dict) -> None:
    if not scenario.get("scenario_id") or scenario.get("level") not in {"M1", "M2"}:
        raise ValueError("scenario_id/level missing or invalid")
    calls = scenario.get("calls")
    if not isinstance(calls, dict) or not calls:
        raise ValueError("scenario must contain calls")
    for index, (name, call) in enumerate(calls.items(), start=1):
        if name != f"call_{index}":
            raise ValueError("calls must be named consecutively from call_1")
        if call.get("channel") not in {"hotline", "chat_fanpage", "zalo_oa"}:
            raise ValueError(f"{name}: invalid channel")
        if not call.get("channel_identity"):
            raise ValueError(f"{name}: channel_identity is required")
        if not isinstance(call.get("customer_turns"), list) or not 4 <= len(call["customer_turns"]) <= 8:
            raise ValueError(f"{name}: expected 4-8 customer turns")
        if any(not isinstance(turn, str) or not turn.strip() for turn in call["customer_turns"]):
            raise ValueError(f"{name}: customer turns must be non-empty strings")
        if call.get("expected_outcome") not in {"hen_goi_lai", "chot_don", "chuyen_may", "tu_choi"}:
            raise ValueError(f"{name}: invalid outcome")
        if not isinstance(call.get("success_if"), dict):
            raise ValueError(f"{name}: success_if is required")


def run(brief_path: Path, dry_run: bool, out_dir: Path | None = None) -> Path:
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    raw, packs = {}, {}
    for call in brief["calls"]:
        index = call["call_index"]
        pack_path = FACT_PACKS_DIR / f"{brief['brief_id']}_c{index}.json"
        raw_path = RAW_DIR / f"{brief['brief_id']}_c{index}.json"
        if not pack_path.exists():
            pack_path.write_text(json.dumps(build_fact_pack(brief, index), ensure_ascii=False, indent=2), encoding="utf-8")
        if not raw_path.exists():
            raise FileNotFoundError(f"Missing raw customer turns {raw_path}; run gen_dialogue first")
        packs[index] = json.loads(pack_path.read_text(encoding="utf-8"))
        raw[index] = json.loads(raw_path.read_text(encoding="utf-8"))
    scenario = assemble_scenario(brief, raw, packs)
    validate_scenario(scenario)
    out_dir = out_dir or (DRYRUN_DIR if dry_run else SCENARIOS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{brief['brief_id']}.json"
    out.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()
    print(run(Path(args.brief), args.dry_run, Path(args.out) if args.out else None))


if __name__ == "__main__":
    main()
