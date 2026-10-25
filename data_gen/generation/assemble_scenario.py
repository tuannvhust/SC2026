from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ..config import BTC_DIR, DRYRUN_DIR, FACT_PACKS_DIR, RAW_DIR, SCENARIOS_DIR
from .facts import build_fact_pack
from .scenario_metadata import (
    customer_goal_for_call,
    hard_case_label,
    scenario_notes,
    scenario_summary_path,
)


def crm_record(brief: dict, customer_id: str | None = None) -> dict:
    customers = json.loads((BTC_DIR / "catalog/crm_seed.json").read_text(encoding="utf-8"))["customers"]
    customer_id = customer_id or brief.get("customer_id")
    return next((c for c in customers if c["customer_id"] == customer_id), {
        "customer_id": customer_id, "name": "Khách hàng", "honorific": "anh/chị", "phone": "<NEW>"
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
        # Match the BTC public_sample contract: one boolean, not per-promotion
        # details or a dump of every promotion considered by the quote tool.
        "promo_active": any(
            bool((item.get("quote") or {}).get("applied_promos"))
            for item in products
        ),
    }
    if inventory.get("restock_expected") is not None:
        result["restock_date"] = inventory["restock_expected"]
    if "freeship" in quote:
        result["freeship"] = quote["freeship"]
    result["policy_chunk_ids"] = [item.get("chunk_id") for item in pack.get("policy", [])]
    result["policy_evidence"] = list(pack.get("policy", []))
    return result


def applied_promo_codes(pack: dict) -> list[str]:
    """Return only promotion codes actually applied by the deterministic quote."""
    codes = []
    for item in pack.get("products", []):
        for promo in (item.get("quote") or {}).get("applied_promos", []):
            code = promo.get("promo_code")
            if code and code not in codes:
                codes.append(code)
    return codes


def assemble_scenario(
    brief: dict,
    raw_by_call: dict[int, dict],
    packs_by_call: dict[int, dict],
    summary: dict | None = None,
) -> dict:
    """Convert reviewed brief + deterministic facts + customer-only turns into evaluator input."""
    customer = crm_record(brief)
    previous_facts_by_customer: dict[str, dict] = {}
    calls = {}
    for call_index in sorted(c["call_index"] for c in brief["calls"]):
        spec = next(c for c in brief["calls"] if c["call_index"] == call_index)
        call_customer_id = spec.get("customer_id", brief.get("customer_id"))
        caller = crm_record(brief, call_customer_id)
        previous_facts = previous_facts_by_customer.setdefault(call_customer_id or "", {})
        pack = packs_by_call[call_index]
        raw = raw_by_call[call_index]
        turns = raw.get("customer_turns")
        if turns is None:  # accept legacy review data, but newly generated data is customer-only
            turns = [item["text"] for item in raw.get("dialogue", []) if item.get("role") == "customer"]
        asr_turns = raw.get("customer_turns_asr")
        if asr_turns is None and isinstance(turns, list):
            # Compatibility for frozen legacy raw records; newly generated raw
            # records always contain an ASR-style variant.
            asr_turns = [re.sub(r"[.!?,;:…]+", "", turn).lower().strip() for turn in turns]

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
        identity = spec.get("channel_identity") or (caller.get(identity_field) if identity_field else caller.get("phone"))
        call_out = {}
        if spec.get("call_date"):
            call_out["call_date"] = pack["call_date"]
        elif spec.get("days_later"):
            call_out["days_later"] = spec["days_later"]
        call_out["channel"] = channel
        call_out["channel_identity"] = identity
        if call_index == 1:
            # A scenario-level LLM summary may describe the primary customer
            # while call_1 belongs to another CRM member (for example shared
            # phone). The public field describes this call, so derive it from
            # this call's reviewed story hint every time.
            call_out["customer_goal"] = customer_goal_for_call(brief, spec)
        input_mode = spec.get("input_mode", brief.get("input_mode", "clean"))
        if input_mode != "clean":
            call_out["input_mode"] = input_mode
        if asr_turns is not None and input_mode != "clean":
            call_out["customer_turns_asr"] = asr_turns
        call_out["customer_turns"] = turns
        previous_facts.update(spec.get("facts_to_establish", {}))
        for item in pack.get("products", []):
            previous_facts["product_advised"] = item.get("sku")
            previous_facts["price_quoted_vnd"] = item.get("quote", {}).get("final_price_vnd")
        applied_promos = applied_promo_codes(pack)
        if applied_promos:
            previous_facts["promo_code"] = applied_promos[0] if len(applied_promos) == 1 else applied_promos
        call_out["facts_established"] = previous_facts.copy()
        for field in (
            "expected_outcome", "must_carry_over", "must_not_ask", "success_if", "seed_history", "memory_expectation",
        ):
            if field in spec:
                call_out[field] = spec[field]
        # Always rebuild evaluator facts from deterministic tool/policy outputs;
        # never trust hand-authored or generated assertions in the brief.
        call_out["ground_truth_facts"] = derive_ground_truth(pack)
        calls[f"call_{call_index}"] = call_out
        

    scenario = {
        "scenario_id": brief["brief_id"],
        "level": brief.get("level", "M1"), "persona": brief["persona_id"],
        "hard_case": hard_case_label(brief.get("hard_case_tags", [])),
        "customer_phone": customer.get("phone"), "customer_name": customer.get("name"),
        "honorific": customer.get("honorific"),
        # Keep notes deterministic and grounded in the reviewed brief. Saved
        # summaries are useful for review, but must not override source facts.
        "notes": scenario_notes(brief),
        "calls": calls,
    }
    return scenario


def validate_scenario(scenario: dict) -> None:
    if not scenario.get("scenario_id") or scenario.get("level") not in {"M1", "M2"}:
        raise ValueError("scenario_id/level missing or invalid")
    scenario_id = scenario["scenario_id"]
    if not re.fullmatch(r"SC-\d{3}", scenario_id) and not scenario_id.startswith("SC-DEMO-"):
        raise ValueError("scenario_id must use SC-NNN")
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
        if not isinstance(call.get("customer_turns"), list) or not 3 <= len(call["customer_turns"]) <= 8:
            raise ValueError(f"{name}: expected 3-8 customer turns")
        if any(not isinstance(turn, str) or not turn.strip() for turn in call["customer_turns"]):
            raise ValueError(f"{name}: customer turns must be non-empty strings")
        asr_turns = call.get("customer_turns_asr")
        if asr_turns is not None and (
            not isinstance(asr_turns, list)
            or len(asr_turns) != len(call["customer_turns"])
            or any(not isinstance(turn, str) or not turn.strip() for turn in asr_turns)
        ):
            raise ValueError(f"{name}: customer_turns_asr must match clean turn count and contain non-empty strings")
        if call.get("expected_outcome") not in {"hen_goi_lai", "chot_don", "chuyen_may", "tu_choi"}:
            raise ValueError(f"{name}: invalid outcome")
        if not isinstance(call.get("success_if"), dict):
            raise ValueError(f"{name}: success_if is required")
        if not isinstance(call.get("ground_truth_facts"), dict):
            raise ValueError(f"{name}: ground_truth_facts is required")


def run(brief_path: Path, dry_run: bool, out_dir: Path | None = None) -> Path:
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    raw, packs = {}, {}
    for call in brief["calls"]:
        index = call["call_index"]
        pack_path = FACT_PACKS_DIR / f"{brief['brief_id']}_c{index}.json"
        raw_path = RAW_DIR / f"{brief['brief_id']}_c{index}.json"
        # Fact packs are deterministic projections of the current brief and BTC
        # reference data. Rebuild them so stale generated packs cannot survive.
        pack_path.write_text(json.dumps(build_fact_pack(brief, index), ensure_ascii=False, indent=2), encoding="utf-8")
        if not raw_path.exists():
            raise FileNotFoundError(f"Missing raw customer turns {raw_path}; run gen_dialogue first")
        packs[index] = json.loads(pack_path.read_text(encoding="utf-8"))
        raw[index] = json.loads(raw_path.read_text(encoding="utf-8"))
    summary_path = scenario_summary_path(RAW_DIR, brief["brief_id"])
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing scenario metadata artifact {summary_path}; run the generation batch first")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("scenario_id") != brief["brief_id"]:
        raise ValueError(f"Scenario metadata artifact does not match {brief['brief_id']}")
    if not isinstance(summary.get("notes"), str) or not summary["notes"].strip():
        raise ValueError(f"{brief['brief_id']}: summary notes are required")
    if not isinstance(summary.get("customer_goal"), str) or not summary["customer_goal"].strip():
        raise ValueError(f"{brief['brief_id']}: summary customer_goal is required")
    scenario = assemble_scenario(brief, raw, packs, summary)
    validate_scenario(scenario)
    out_dir = out_dir or (DRYRUN_DIR if dry_run else SCENARIOS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{brief['brief_id']}.json"
    out.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_dir = out_dir.with_name(f"{out_dir.name}_metadata")
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "scenario_id": brief["brief_id"],
        "case_number": brief.get("case_number"),
        "customer_id": brief.get("customer_id"),
        "call_customer_ids": {
            f"call_{call['call_index']}": call.get("customer_id", brief.get("customer_id"))
            for call in brief["calls"]
        },
        "call_customer_names": {
            f"call_{call['call_index']}": crm_record(brief, call.get("customer_id", brief.get("customer_id"))).get("name")
            for call in brief["calls"]
        },
        "teencode_levels": {
            f"call_{call['call_index']}": call.get("teencode_level", "light" if call.get("input_mode") == "chat_teencode" else "none")
            for call in brief["calls"]
        },
        "story_hints": {
            f"call_{call['call_index']}": call.get("story_hint", "")
            for call in brief["calls"]
        },
        "scenario_metadata_generation": summary.get("generation_meta", {}),
    }
    (metadata_dir / f"{brief['brief_id']}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
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
