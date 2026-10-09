from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .config import FACT_PACKS_DIR, MODEL, PROMPT_VERSION, RAW_DIR, BTC_DIR
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


def parse_dialogue(text: str) -> list[dict]:
    text=re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()).strip()
    dialogue=json.loads(text)
    if not isinstance(dialogue, list) or not 8 <= len(dialogue) <= 16: raise ValueError("dialogue must contain 8-16 turns")
    if any(set(item) != {"role", "text"} or item["role"] not in {"customer", "agent"} or not isinstance(item["text"], str) for item in dialogue): raise ValueError("invalid role/text shape")
    return dialogue


def run(brief: dict, call_index: int, seed: int, dry_run: bool) -> Path:
    call=next(c for c in brief["calls"] if c["call_index"] == call_index)
    pack=build_fact_pack(brief, call_index)
    prompt=(Path(__file__).parent / "prompts/dialogue_v1.txt").read_text(encoding="utf-8")
    prompt_pack=json.loads(json.dumps(pack))
    for product in prompt_pack.get("products", []):
        product.get("quote", {}).pop("_internal_price_floor_vnd", None)
    prompt_pack.pop("internal_policy_ids", None)
    payload={"fact_pack": prompt_pack, "persona": persona_record(brief["persona_id"]), "crm_profile": pack["customer"], "must_not_ask": [], "must_carry_over": [], "previous_call_summary": structured_previous_summary(brief, call_index), "call_goal": call["customer_goal"], "channel": brief["channel"], "call": call}
    text=complete(prompt, json.dumps(payload, ensure_ascii=False), seed=seed, temperature=0, dry_run=dry_run)
    dialogue=parse_dialogue(text)
    result={"brief_id": brief["brief_id"], "call_index": call_index, "dialogue": dialogue, "generation_meta":{"prompt_version":PROMPT_VERSION,"model":"dry-run" if dry_run else MODEL,"seed":seed,"dry_run":dry_run}}
    out=RAW_DIR / f"{brief['brief_id']}_c{call_index}.json"; out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--brief", required=True); ap.add_argument("--call", type=int, required=True); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--seed", type=int, default=7); args=ap.parse_args()
    brief=json.loads(Path(args.brief).read_text(encoding="utf-8")); print(run(brief, args.call, args.seed, args.dry_run))


if __name__ == "__main__": main()
