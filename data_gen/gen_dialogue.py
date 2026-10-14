from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from .config import FACT_PACKS_DIR, MODEL, PROMPT_VERSION, PROVIDER, RAW_DIR, BTC_DIR
from .facts import calls_by_index
from .llm_client import complete


def persona_record(persona_id: str) -> dict:
    data=json.loads((BTC_DIR / "simulator/personas.json").read_text(encoding="utf-8"))
    return next(p for p in data["personas"] if p["persona_id"] == persona_id)


def generation_prompt(persona_id: str, call: dict, scenario_num_calls: int | None = None) -> tuple[str, str]:
    """Return the shared contract plus the selected, rendered customer persona prompt."""
    template = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt").read_text(encoding="utf-8")
    persona = persona_record(persona_id)
    call_index = int(call.get("call_index", 1))
    scenario_num_calls = int(scenario_num_calls or call_index)
    patience_initial = persona.get("patience_initial", {}).get(f"call_{call_index}")
    facts = json.dumps(call.get("facts_to_establish", {}), ensure_ascii=False, sort_keys=True)
    outline = call.get("story_hint", "")
    specific = persona.get("system_prompt", "")
    for key, value in {
        "goal": call.get("customer_goal", ""),
        "facts": facts,
        "turn_outline": outline,
    }.items():
        specific = specific.replace("{" + key + "}", str(value))
    persona_context = (
        "\n\nNgữ cảnh persona cho cuộc gọi này (dùng để điều chỉnh cách nói và phản ứng):"
        f"\n- Style: {persona.get('style', '')}"
        f"\n- Vị trí cuộc gọi: {call_index}/{scenario_num_calls} trong scenario của cùng khách hàng."
        f"\n- Patience ban đầu của cuộc gọi: {patience_initial if patience_initial is not None else 'không khai báo'}"
    )
    # Persona instructions shape customer behavior; shared constraints retain the
    # customer-only output contract and prohibit invented/unsafe facts.
    system = f"{specific}{persona_context}\n\nQuy tắc chung bắt buộc:\n{template}"
    digest = hashlib.sha256(
        json.dumps({"version": PROMPT_VERSION, "system": system}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return system, digest


def structured_previous_summary(brief: dict, call_index: int) -> dict:
    previous=[]
    for call in brief.get("calls", []):
        if call["call_index"] >= call_index: break
        previous.append({"facts_established_by_customer": call.get("facts_to_establish", {}), "customer_story": call.get("story_hint", "")})
    return {"calls": previous}


def generation_payload(brief: dict, call_index: int) -> dict:
    """Build the structured user message, including per-call persona context."""
    call = next(c for c in brief["calls"] if c["call_index"] == call_index)
    persona = persona_record(brief["persona_id"])
    return {
        "persona": {
            "persona_id": persona["persona_id"],
            "style": persona.get("style", ""),
            "patience_initial": persona.get("patience_initial", {}).get(f"call_{call_index}"),
        },
        "call_index": call_index,
        "scenario_num_calls": len(brief["calls"]),
        "call_goal": call["customer_goal"],
        "story_hint": call.get("story_hint", ""),
        "facts_established": call.get("facts_to_establish", {}),
        "previous_customer_facts": structured_previous_summary(brief, call_index),
        "channel": call.get("channel", brief["channel"]),
        "input_mode": call.get("input_mode", "clean"),
    }


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


def parse_customer_turns(text: str) -> list[str]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()).strip()
    turns = json.loads(text)
    if not isinstance(turns, list) or not 4 <= len(turns) <= 8:
        raise ValueError("customer_turns must contain 4-8 customer turns")
    if any(not isinstance(turn, str) or not turn.strip() for turn in turns):
        raise ValueError("customer_turns must be a JSON array of non-empty strings")
    return [turn.strip() for turn in turns]


def run(brief: dict, call_index: int, seed: int, dry_run: bool) -> Path:
    call=next(c for c in brief["calls"] if c["call_index"] == call_index)
    scenario_num_calls = len(brief["calls"])
    prompt, prompt_digest = generation_prompt(brief["persona_id"], call, scenario_num_calls)
    payload = generation_payload(brief, call_index)
    text=complete(prompt, json.dumps(payload, ensure_ascii=False), seed=seed, temperature=0, dry_run=dry_run)
    customer_turns=parse_customer_turns(text)
    result={"brief_id": brief["brief_id"], "call_index": call_index, "customer_turns": customer_turns, "generation_meta":{"provider":"dry-run" if dry_run else PROVIDER,"prompt_version":PROMPT_VERSION,"prompt_digest":prompt_digest,"model":"dry-run" if dry_run else MODEL,"seed":seed,"dry_run":dry_run}}
    out=RAW_DIR / f"{brief['brief_id']}_c{call_index}.json"; out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--brief", required=True); ap.add_argument("--call", type=int, required=True); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--seed", type=int, default=7); args=ap.parse_args()
    brief=json.loads(Path(args.brief).read_text(encoding="utf-8")); print(run(brief, args.call, args.seed, args.dry_run))


if __name__ == "__main__": main()
