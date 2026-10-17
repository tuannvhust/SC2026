from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from .config import FACT_PACKS_DIR, MODEL, PROMPT_VERSION, PROVIDER, RAW_DIR, BTC_DIR
from .llm_client import complete


PUBLIC_ATTRIBUTE_KEYS = {
    "features", "material", "room_area_m2", "warranty_months", "child_safe_lock",
    "stages", "max_weight_kg", "volume_ml",
}
INPUT_MODE_PROMPT_PATH = Path(__file__).parent / "prompts" / "customer_input_modes_v1.txt"
INPUT_MODE_PROMPT = INPUT_MODE_PROMPT_PATH.read_text(encoding="utf-8").strip()
ASR_SYSTEM_PROMPT = (
    "Bạn biến đổi từng lượt trong clean_customer_turns theo input_mode và teencode_level của payload, "
    "theo đúng quy tắc bên dưới. Không viết hội thoại mới. Trả về duy nhất mảng JSON có cùng số phần tử "
    "và đúng thứ tự.\n\n"
    + INPUT_MODE_PROMPT
)


def visible_product_context(call: dict) -> list[dict]:
    """Return customer-visible catalog descriptions without SKU, price, or stock."""
    catalog = json.loads((BTC_DIR / "catalog/products.json").read_text(encoding="utf-8"))
    products = catalog.get("products", [])
    result = []
    for requested in call.get("products", []):
        requested_sku = requested.get("variant_id") or requested.get("sku")

        parent = next((p for p in products if p.get("sku") == requested_sku or any(
            v.get("variant_sku") == requested_sku for v in p.get("variants", [])
        )), None)
        if not parent:
            continue

        public_name = re.sub(r"\s*[—-]\s*NGỪNG BÁN\s*$", "", parent.get("name", ""), flags=re.IGNORECASE)

        details = {k: v for k, v in parent.get("attributes", {}).items() if k in PUBLIC_ATTRIBUTE_KEYS}

        visible = {
            "name": public_name,
            "brand": parent.get("brand"),
            "category": parent.get("category", "").replace("/", " "),
            "public_details": details,
        }

        variant = next((v for v in parent.get("variants", []) if v.get("variant_sku") == requested_sku), None)
        if variant:
            for key in ("size", "color"):
                if variant.get(key) is not None:
                    visible[key] = variant[key]
        result.append({k: v for k, v in visible.items() if v not in (None, "", {})})

    return result


def customer_facts_for_generation(call: dict, visible_products: list[dict]) -> dict:
    """Replace internal product identifiers with the customer-facing product name."""
    facts = dict(call.get("facts_to_establish", {}))
    sku_to_name = {}
    products = json.loads((BTC_DIR / "catalog/products.json").read_text(encoding="utf-8"))
    for requested, visible in zip(call.get("products", []), visible_products):
        sku_to_name[requested.get("sku")] = visible.get("name")
        if requested.get("variant_id"):
            sku_to_name[requested["variant_id"]] = visible.get("name")
    advised = facts.get("product_advised")
    if advised in sku_to_name:
        facts["product_advised"] = sku_to_name[advised]
    # Drop any additional identifier-shaped slots rather than teach them to the customer simulator.
    for key in list(facts):
        if key.lower() in {"sku", "variant_id", "variant_sku", "product_id"}:
            facts.pop(key)
        elif isinstance(facts[key], str) and facts[key] in sku_to_name:
            facts[key] = sku_to_name[facts[key]]
    return facts


def persona_record(persona_id: str) -> dict:
    data=json.loads((BTC_DIR / "simulator/personas.json").read_text(encoding="utf-8"))
    return next(p for p in data["personas"] if p["persona_id"] == persona_id)


def customer_record(customer_id: str | None, brief: dict) -> dict:
    if not customer_id:
        return {"customer_id": brief.get("customer_id"), "name": brief.get("customer_name"), "honorific": brief.get("honorific")}
    crm = json.loads((BTC_DIR / "catalog/crm_seed.json").read_text(encoding="utf-8"))["customers"]
    return next((c for c in crm if c.get("customer_id") == customer_id), {})


def generation_prompt(persona_id: str, call: dict, scenario_num_calls: int | None = None) -> tuple[str, str]:
    """Return the shared contract plus the selected, rendered customer persona prompt."""
    template = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.txt").read_text(encoding="utf-8")
    persona = persona_record(persona_id)
    call_index = int(call.get("call_index", 1))
    scenario_num_calls = int(scenario_num_calls or call_index)
    patience_initial = persona.get("patience_initial", {}).get(f"call_{call_index}")
    public_products = visible_product_context(call)
    customer = customer_record(call.get("customer_id"), {})
    facts = json.dumps(
        customer_facts_for_generation(call, public_products),
        ensure_ascii=False,
        sort_keys=True,
    )
    outline = call.get("story_hint", "")
    specific = persona.get("system_prompt", "")
    honorific = customer.get("honorific")
    self_pronoun = {"anh": "anh", "chị": "chị", "cô": "cô"}.get(honorific, "mình")
    for key, value in {
        "goal": outline,
        "facts": facts,
        "turn_outline": outline,
    }.items():
        specific = specific.replace("{" + key + "}", str(value))
    persona_context = (
        "\n\nNgữ cảnh persona cho cuộc gọi này (dùng để điều chỉnh cách nói và phản ứng):"
        f"\n- Style: {persona.get('style', '')}"
        f"\n- Vị trí cuộc gọi: {call_index}/{scenario_num_calls} trong scenario của cùng khách hàng."
        f"\n- Patience ban đầu của cuộc gọi: {patience_initial if patience_initial is not None else 'không khai báo'}"
        + (f"\n- Người đang liên hệ trong cuộc gọi này: {customer.get('honorific', '')} {customer.get('name', '')}." if customer.get("name") else "")
        + (f"\n- Cách xưng hô bắt buộc: khách tự xưng ‘{self_pronoun}’, gọi nhân viên là ‘em’; giữ đúng honorific ‘{honorific}’ nếu cần xưng hô." if honorific else "")
    )
    product_context = (
        "\n\nMô tả sản phẩm công khai khách có thể biết từ website/bài đăng "
        "(chỉ dùng tên và đặc điểm dưới đây; khách không biết SKU):\n"
        + json.dumps(public_products, ensure_ascii=False)
        + "\nKhông tự thêm thuộc tính, giá, khuyến mãi, tồn kho hoặc kết quả tra cứu."
        if public_products else ""
    )
    # Persona instructions shape customer behavior; shared constraints retain the
    # customer-only output contract and prohibit invented/unsafe facts.
    system = (
        f"{specific}{persona_context}{product_context}\n\nQuy tắc chung bắt buộc:\n{template}"
        "\n\n`customer_turns` luôn là bản chuẩn tự nhiên, có dấu. Không tạo teencode hoặc lỗi ASR ở đây; "
        "các biến thể được tạo riêng trong `customer_turns_asr`."
    )
    digest = hashlib.sha256(
        json.dumps({"version": PROMPT_VERSION, "system": system}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return system, digest


def structured_previous_summary(brief: dict, call_index: int) -> dict:
    previous=[]
    current = next(c for c in brief["calls"] if c["call_index"] == call_index)
    current_customer_id = current.get("customer_id", brief.get("customer_id"))
    for call in brief.get("calls", []):
        if call["call_index"] >= call_index: break
        if current_customer_id and call.get("customer_id", brief.get("customer_id")) != current_customer_id:
            continue
        visible = visible_product_context(call)
        previous.append({
            "facts_established_by_customer": customer_facts_for_generation(call, visible),
            "customer_story": call.get("story_hint", ""),
            "visible_products": visible,
        })
    return {"calls": previous}


def generation_payload(brief: dict, call_index: int) -> dict:
    """Build the structured user message, including per-call persona context."""
    call = next(c for c in brief["calls"] if c["call_index"] == call_index)
    persona = persona_record(brief["persona_id"])
    customer = customer_record(call.get("customer_id"), brief)
    visible_products = visible_product_context(call)
    facts_established = customer_facts_for_generation(call, visible_products)
    return {
        "persona": {
            "persona_id": persona["persona_id"],
            "style": persona.get("style", ""),
            "patience_initial": persona.get("patience_initial", {}).get(f"call_{call_index}"),
        },
        "caller_identity": {
            "name": customer.get("name"),
            "honorific": customer.get("honorific"),
            "must_identify_as_this_person": bool(call.get("customer_id")),
        },
        "call_index": call_index,
        "scenario_num_calls": len(brief["calls"]),
        "story_hint": call.get("story_hint", ""),
        "expected_outcome": call.get("expected_outcome"),
        "facts_established": facts_established,
        "visible_products": visible_products,
        "previous_customer_facts": structured_previous_summary(brief, call_index),
        "channel": call.get("channel", brief["channel"]),
        "input_mode": call.get("input_mode", "clean"),
        "teencode_level": call.get("teencode_level", "light" if call.get("input_mode") == "chat_teencode" else "none"),
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
            "story_hint": call.get("story_hint", ""),
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


def generate_turn_array(system: str, payload: dict, *, seed: int, dry_run: bool, expected_count: int | None = None) -> list[str]:
    """Retry malformed model output with a deterministic validation repair prompt."""
    last_error = "unknown output error"
    facts = payload.get("facts_established", {})
    required_address = facts.get("customer_address_to_confirm") if facts.get("address_confirmed") is True else None
    for attempt in range(3):
        request = dict(payload)
        if attempt:
            request["format_correction"] = (
                f"Lần trước không hợp lệ: {last_error}. Hãy tạo lại duy nhất một JSON array "
                "đúng 4-8 chuỗi khách hàng, không thiếu hoặc thừa phần tử."
            )
            if required_address:
                request["format_correction"] += f" Include this exact address in one customer turn: {required_address}."
        text = complete(
            system,
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            seed=seed + attempt,
            temperature=0,
            dry_run=dry_run,
        )
        try:
            turns = parse_customer_turns(text)
            if expected_count is not None and len(turns) != expected_count:
                raise ValueError(f"expected {expected_count} turns, got {len(turns)}")
            if required_address and required_address not in " ".join(turns):
                raise ValueError("customer turns must include the exact CRM delivery address to confirm")
            return turns
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
    raise ValueError(f"model output invalid after 3 attempts: {last_error}")


def make_asr_turns(
    clean_turns: list[str],
    *,
    seed: int,
    dry_run: bool,
    input_mode: str = "asr_transcript",
    teencode_level: str = "light",
) -> list[str]:
    """Create the declared ASR/teencode input variant (no audio is synthesized)."""
    if dry_run:
        if input_mode == "chat_teencode":
            replacements = [("không", "ko"), ("được", "đc"), ("mình", "mk"), ("sản phẩm", "sp")]
            if teencode_level == "heavy":
                replacements += [("bao nhiêu", "bnhiu"), ("gì", "j"), ("vậy", "z")]
            result = []
            for turn in clean_turns:
                for source, target in replacements:
                    turn = re.sub(rf"\b{re.escape(source)}\b", target, turn, count=1, flags=re.IGNORECASE)
                result.append(turn)
            return result
        if input_mode == "asr_transcript":
            return [re.sub(r"[.!?,;:…]+", "", turn).lower().strip() for turn in clean_turns]
        return list(clean_turns)

    return generate_turn_array(
        ASR_SYSTEM_PROMPT,
        {
            "input_mode": input_mode,
            "teencode_level": teencode_level,
            "clean_customer_turns": clean_turns,
        },
        seed=seed + 1,
        dry_run=False,
        expected_count=len(clean_turns),
    )


def run(brief: dict, call_index: int, seed: int, dry_run: bool) -> Path:
    call=next(c for c in brief["calls"] if c["call_index"] == call_index)
    scenario_num_calls = len(brief["calls"])
    prompt, prompt_digest = generation_prompt(brief["persona_id"], call, scenario_num_calls)
    payload = generation_payload(brief, call_index)
    # customer_turns is the canonical clean text; ASR-style text is generated
    # separately from this exact turn list below.
    payload["input_mode"] = "clean"
    payload["teencode_level"] = "none"
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload_digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    customer_turns = generate_turn_array(prompt, payload, seed=seed, dry_run=dry_run)
    requested_mode = call.get("input_mode", "clean")
    variant_mode = requested_mode if requested_mode in {"chat_teencode", "asr_transcript"} else "asr_transcript"
    customer_turns_asr=make_asr_turns(
        customer_turns,
        seed=seed,
        dry_run=dry_run,
        input_mode=variant_mode,
        teencode_level=call.get("teencode_level", "light"),
    )
    result={
        "brief_id": brief["brief_id"], 
        "call_index": call_index, 
        "customer_turns": customer_turns, 
        "customer_turns_asr": customer_turns_asr, 
        "generation_meta":{
            "provider":"dry-run" if dry_run else PROVIDER,
            "prompt_version":PROMPT_VERSION,
            "prompt_digest":prompt_digest,
            "asr_prompt_digest":hashlib.sha256(ASR_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "payload_digest":payload_digest,
            "asr_input_digest":hashlib.sha256(json.dumps(customer_turns,ensure_ascii=False).encode("utf-8")).hexdigest(),
            "format_repair_attempts_max":3,
            "model":"dry-run" if dry_run else MODEL,
            "seed":seed,
            "asr_seed":seed + 1,
            "dry_run":dry_run
        }
    }
    out=RAW_DIR / f"{brief['brief_id']}_c{call_index}.json" 
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--brief", required=True)
    ap.add_argument("--call", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=7)

    args=ap.parse_args()

    brief=json.loads(Path(args.brief).read_text(encoding="utf-8"))
    print(run(brief, args.call, args.seed, args.dry_run))


if __name__ == "__main__": main()
