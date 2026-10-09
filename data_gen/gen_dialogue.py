from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .config import FACT_PACKS_DIR, MODEL, PROMPT_VERSION, PROVIDER, RAW_DIR, BTC_DIR
from .facts import build_fact_pack, calls_by_index
from .llm_client import complete


def persona_record(persona_id: str) -> dict:
    data=json.loads((BTC_DIR / "simulator/personas.json").read_text(encoding="utf-8"))
    return next(p for p in data["personas"] if p["persona_id"] == persona_id)


def structured_previous_summary(brief: dict, call_index: int) -> dict:
    previous=[]
    for call in brief.get("calls", []):
        if call["call_index"] >= call_index: break
        previous.append({"call_index": call["call_index"], "facts_to_establish": call.get("facts_to_establish", {}), "goal": call.get("customer_goal"), "outcome": call.get("expected_outcome")})
    return {"calls": previous}


def dialogue_constraints(brief: dict, call_index: int, pack: dict) -> tuple[list[str], list[dict]]:
    """Build prompt constraints from structured data; never ask the LLM to derive them."""
    previous_facts: dict = {}
    previous_calls: list[dict] = []
    for call in brief.get("calls", []):
        if call["call_index"] >= call_index:
            break
        previous_facts.update(call.get("facts_to_establish", {}))
        previous_calls.append({
            "call_index": call["call_index"],
            "facts_to_establish": call.get("facts_to_establish", {}),
            "products": call.get("products", []),
            "customer_goal": call.get("customer_goal"),
            "expected_outcome": call.get("expected_outcome"),
        })
    crm = pack.get("customer", {}).get("crm", {}) or {}
    known_slots = {"customer_id", "customer_name", "honorific"}
    if crm.get("name"):
        known_slots.add("customer_name")
    if crm.get("honorific"):
        known_slots.add("honorific")
    known_slots.update(previous_facts)
    carry = []
    if previous_calls:
        carry.append({"previous_calls": previous_calls})
    if previous_facts:
        carry.append({"previous_facts": previous_facts})
    return sorted(known_slots), carry


def parse_dialogue(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()).strip()
    dialogue = json.loads(text)

    if not isinstance(dialogue, list) or not 8 <= len(dialogue) <= 16:
        raise ValueError("dialogue must contain 8-16 turns")

    for index, item in enumerate(dialogue):
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "text"}
            or item.get("role") not in {"customer", "agent"}
            or not isinstance(item.get("text"), str)
        ):
            raise ValueError(
                f"invalid role/text shape at turn {index}: {item!r}"
            )
    return dialogue


def run(brief: dict, call_index: int, seed: int, dry_run: bool) -> Path:
    call=next(c for c in brief["calls"] if c["call_index"] == call_index)
    pack=build_fact_pack(brief, call_index)
    prompt=(Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt").read_text(encoding="utf-8")
    prompt_pack=json.loads(json.dumps(pack))
    for product in prompt_pack.get("products", []):
        product.get("quote", {}).pop("_internal_price_floor_vnd", None)
    prompt_pack["policy"] = [item for item in prompt_pack.get("policy", []) if item.get("type") != "internal"]
    prompt_pack.pop("internal_policy_ids", None)
    must_not_ask, must_carry_over = dialogue_constraints(brief, call_index, pack)
    payload={"fact_pack": prompt_pack, "persona": persona_record(brief["persona_id"]), "crm_profile": pack["customer"], "must_not_ask": must_not_ask, "must_carry_over": must_carry_over, "previous_call_summary": structured_previous_summary(brief, call_index), "call_goal": call["customer_goal"], "channel": brief["channel"], "call": call}
    text=complete(prompt, json.dumps(payload, ensure_ascii=False), seed=seed, temperature=0, dry_run=dry_run)
    dialogue=parse_dialogue(text)
    result={"brief_id": brief["brief_id"], "call_index": call_index, "dialogue": dialogue, "generation_meta":{"provider":"dry-run" if dry_run else PROVIDER,"prompt_version":PROMPT_VERSION,"model":"dry-run" if dry_run else MODEL,"seed":seed,"dry_run":dry_run}}
    out=RAW_DIR / f"{brief['brief_id']}_c{call_index}.json"; out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--brief", required=True); ap.add_argument("--call", type=int, required=True); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--seed", type=int, default=7); args=ap.parse_args()
    brief=json.loads(Path(args.brief).read_text(encoding="utf-8")); print(run(brief, args.call, args.seed, args.dry_run))


if __name__ == "__main__": main()
