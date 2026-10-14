from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .config import BTC_DIR, BRIEFS_DIR, REPORTS_DIR


def btc_data() -> dict:
    def load(p): return json.loads((BTC_DIR / p).read_text(encoding="utf-8"))
    products = load("catalog/products.json")["products"]
    sku_category = {p["sku"]: p["category"].split("/", 1)[0] for p in products}
    for p in products:
        sku_category.update({v["variant_sku"]: p["category"].split("/", 1)[0] for v in p.get("variants", [])})
    variants = {v["variant_sku"] for p in products for v in p.get("variants", [])}
    variant_sizes = {v["variant_sku"]: v.get("size") for p in products for v in p.get("variants", [])}
    skus = {p["sku"] for p in products} | variants
    crm = load("catalog/crm_seed.json")["customers"]
    promos = {p["promo_code"] for p in load("catalog/promotions.json")["promotions"]}
    chunks = set()
    for path in (BTC_DIR / "policy").glob("*.md"):
        chunks.update(re.findall(r"\[([A-Z0-9-]+)\]", path.read_text(encoding="utf-8")))
    personas = {p["persona_id"] for p in load("simulator/personas.json")["personas"]}
    return {"skus": skus, "sku_category": sku_category, "variant_sizes": variant_sizes, "crm": {c["customer_id"] for c in crm}, "customers": {c["customer_id"]: c for c in crm}, "promos": promos, "chunks": chunks, "personas": personas}


def validate_hard_case(brief: dict, ref: dict) -> list[str]:
    """Check that planned hard-case tags have matching structured test content."""
    errors = []
    tags = set(brief.get("hard_case_tags", []))
    calls = brief.get("calls", [])
    if not tags:
        return errors
    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(f"hard_case {','.join(sorted(tags))}: {message}")
    if "shared_phone" in tags:
        customer = ref["customers"].get(brief.get("customer_id"), {})
        require(bool(customer.get("shared_phone_with")), "customer must be a shared-phone CRM record")
        require(any(call.get("facts_to_establish", {}).get("caller_identity") for call in calls), "caller identity confirmation must be represented")
    if "ttl_long_history" in tags:
        require(any(call.get("facts_to_establish", {}).get("customer_history_months") == 8 for call in calls), "must encode the 8-month history")
    if "version_conflict" in tags:
        require(any(call.get("facts_to_establish", {}).get("purchase_date") == "2026-06-15" for call in calls), "must encode a pre-2026-10-01 purchase date")
        require(any(any(chunk.startswith("DT-OLD-") for chunk in call.get("policy_chunk_ids", [])) for call in calls), "must reference an old policy chunk")
    if "unanswerable" in tags:
        require(all(call.get("expected_outcome") == "tu_choi" and call.get("success_if", {}).get("tool_called") is None and "handoff.transfer" in call.get("success_if", {}).get("must_not_call_tools", []) for call in calls), "must assert no-info refusal without handoff/tools")
    if "three_channel_price_conflict" in tags:
        channels = {call.get("channel") for call in calls}
        require(len(calls) == 3 and channels == {"hotline", "zalo_oa", "chat_fanpage"}, "must contain calls on hotline, Zalo and Fanpage")
    if "size_excluded_promotion" in tags:
        require(any(ref["variant_sizes"].get(product.get("variant_id")) == 43 for call in calls for product in call.get("products", [])), "must select a size-43 variant")
        require(any(call.get("promo_codes_in_play") for call in calls), "must include a promotion to check against the excluded size")
    if "pii_cccd_bank_account" in tags:
        require(any(call.get("facts_to_establish", {}).get("sensitive_data_offer") == "redacted_only" for call in calls), "must exercise only redacted synthetic PII")
    if "order_in_transit" in tags:
        require(all(call.get("success_if", {}).get("tool_called") == "order.status" for call in calls), "must test order status lookup")
    if "three_call_order_status" in tags:
        require(len(calls) == 3 and all(call.get("success_if", {}).get("tool_called") == "order.status" for call in calls), "must check order status over three calls")
    if "multi_product_cod_budget" in tags:
        require(all(len({p.get("sku") for p in call.get("products", [])}) >= 4 for call in calls), "must contain at least four distinct products per call")
        require(all(call.get("facts_to_establish", {}).get("budget_vnd") == 8000000 for call in calls), "must include the budget constraint")
        require(all(call.get("success_if", {}).get("tool_called") is None and "order.create" in call.get("success_if", {}).get("must_not_call_tools", []) for call in calls), "must prevent order creation over budget/COD limit")
    if "ai_identity_data_deletion" in tags:
        require(all(call.get("success_if", {}).get("tool_called") is None and "order.create" in call.get("success_if", {}).get("must_not_call_tools", []) for call in calls), "must not turn a data-deletion request into an order")
        require(any(call.get("success_if", {}).get("must_say_any") for call in calls), "must test an honest AI identity response")
    if "product_exchange_refund_difference" in tags:
        require(all(call.get("success_if", {}).get("tool_called") == "order.update" for call in calls), "must test an exchange/update action")
    if "callback_holiday" in tags:
        require(any(call.get("expected_outcome") == "hen_goi_lai" and call.get("facts_to_establish", {}).get("callback_requested_at") == "2026-10-26T09:00" and call.get("success_if", {}).get("tool_called") == "schedule.callback" and call.get("success_if", {}).get("args_match", {}).get("callback_at") == "2026-10-26T09:00" for call in calls), "must assert a callback outcome on the 2026-10-26 holiday")
    if "inventory_runs_out_at_close" in tags:
        require(len(calls) >= 2 and any(product.get("variant_id") for call in calls for product in call.get("products", [])), "must use a dated variant stock change over multiple calls")
    return errors


def lint_one(path: Path, ref: dict) -> list[str]:
    errors = []
    try: brief = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc: return [f"invalid JSON: {exc}"]
    for key in ("brief_id", "persona_id", "customer_id", "channel", "calls"):
        if key not in brief: errors.append(f"missing {key}")
    if brief.get("level", "M1") not in {"M1", "M2"}: errors.append("level must be M1 or M2")
    if "case_number" in brief and (not isinstance(brief["case_number"], int) or brief["case_number"] < 1): errors.append("case_number must be a positive integer")
    if brief.get("persona_id") not in ref["personas"]: errors.append("invalid persona_id")
    customer = str(brief.get("customer_id", ""))
    if not (customer.startswith("NEW:") or customer in ref["crm"]): errors.append("invalid customer_id")
    if not isinstance(brief.get("calls"), list) or not brief.get("calls"):
        errors.append("calls must be a non-empty list")
        return errors
    errors.extend(validate_hard_case(brief, ref))
    indices = [c.get("call_index") for c in brief.get("calls", [])]
    if indices != list(range(1, len(indices) + 1)): errors.append("call_index must be continuous from 1")
    crm = ref["customers"].get(customer)
    hints = brief.get("_matrix_hints", {})
    expected_pattern = hints.get("channel_pattern", "").split("-") if hints.get("channel_pattern") else []
    if crm:
        if hints.get("customer_id") and hints["customer_id"] != customer:
            errors.append("customer_id differs from reviewed matrix assignment")
        if hints.get("persona_id") and hints["persona_id"] != brief.get("persona_id"):
            errors.append("persona_id differs from reviewed matrix assignment")
    valid_outcomes = {"hen_goi_lai", "chot_don", "chuyen_may", "tu_choi"}
    for call in brief.get("calls", []):
        channel = call.get("channel", brief.get("channel"))
        if channel not in {"hotline", "chat_fanpage", "zalo_oa"}: errors.append(f"call {call.get('call_index')}: invalid channel")
        if crm and channel:
            identity_key = {"hotline": "phone", "chat_fanpage": "fb_id", "zalo_oa": "zalo_id"}[channel]
            identity = call.get("channel_identity", crm.get(identity_key))
            if not identity or (identity_key != "phone" and identity != crm.get(identity_key)):
                errors.append(f"call {call.get('call_index')}: missing/mismatched CRM channel_identity")
        call_index = call.get("call_index", 1)
        if expected_pattern and call_index <= len(expected_pattern) and channel != expected_pattern[call_index - 1]:
            errors.append(f"call {call_index}: channel differs from reviewed matrix pattern")
        days_later = call.get("days_later", 0)
        if not isinstance(days_later, (int, float)) or isinstance(days_later, bool): errors.append(f"call {call.get('call_index')}: days_later must be numeric")
        elif days_later < 0: errors.append(f"call {call.get('call_index')}: days_later < 0")
        if call.get("expected_outcome") not in valid_outcomes:
            errors.append(f"call {call.get('call_index')}: invalid expected_outcome")
        if call.get("expected_outcome") == "TODO":
            errors.append(f"call {call.get('call_index')}: expected_outcome is TODO")
        condition = call.get("success_if")
        if condition is not None and not isinstance(condition, dict):
            errors.append(f"call {call.get('call_index')}: success_if must be an object")
        elif isinstance(condition, dict):
            if "must_not_call_tools" in condition and not isinstance(condition["must_not_call_tools"], list):
                errors.append(f"call {call.get('call_index')}: success_if.must_not_call_tools must be a list")
            if "must_say_any" in condition and not isinstance(condition["must_say_any"], list):
                errors.append(f"call {call.get('call_index')}: success_if.must_say_any must be a list")
            if "max_agent_questions" in condition and (not isinstance(condition["max_agent_questions"], int) or condition["max_agent_questions"] < 0):
                errors.append(f"call {call.get('call_index')}: success_if.max_agent_questions must be a non-negative integer")
        for required in ("customer_goal", "story_hint"):
            if not isinstance(call.get(required), str) or not call[required].strip() or "TODO" in call[required].upper():
                errors.append(f"call {call.get('call_index')}: {required} is missing or TODO")
        products = call.get("products", [])
        if not isinstance(products, list): errors.append(f"call {call.get('call_index')}: products must be a list")
        for product in products if isinstance(products, list) else []:
            if not isinstance(product, dict): errors.append(f"call {call.get('call_index')}: product entry must be an object"); continue
            if product.get("sku") in {None, "", "TODO"}: errors.append(f"call {call.get('call_index')}: product SKU is missing")
            if product.get("sku") not in ref["skus"]: errors.append(f"call {call.get('call_index')}: invalid SKU")
            if product.get("variant_id") and product["variant_id"] not in ref["skus"]: errors.append(f"call {call.get('call_index')}: invalid variant_id")
            assigned_industry = brief.get("_matrix_hints", {}).get("nganh")
            actual_industry = ref["sku_category"].get(product.get("variant_id") or product.get("sku"))
            if assigned_industry and actual_industry and assigned_industry != actual_industry:
                errors.append(f"call {call.get('call_index')}: SKU category {actual_industry} differs from matrix {assigned_industry}")
            if not isinstance(product.get("qty", 1), int) or product.get("qty", 1) < 1: errors.append(f"call {call.get('call_index')}: qty must be a positive integer")
        for promo in call.get("promo_codes_in_play", []):
            if promo not in ref["promos"]: errors.append(f"call {call.get('call_index')}: invalid promotion")
        for chunk in call.get("policy_chunk_ids", []):
            if chunk not in ref["chunks"]: errors.append(f"call {call.get('call_index')}: invalid policy chunk")
        for field in ("promo_codes_in_play", "policy_chunk_ids"):
            if not isinstance(call.get(field, []), list):
                errors.append(f"call {call.get('call_index')}: {field} must be a list")
        for key in call.get("facts_to_establish", {}):
            if re.search(r"price_|promo_|discount|final_price|list_price", key, re.I): errors.append(f"call {call.get('call_index')}: forbidden factual key {key}")
        facts_text = json.dumps(call.get("facts_to_establish", {}), ensure_ascii=False)
        if re.search(r"(?<!\d)0\d{9}(?!\d)|\b0\d{11}\b|[\w.+-]+@[\w.-]+", facts_text): errors.append(f"call {call.get('call_index')}: unmasked PII in facts_to_establish")
        asr_turns = call.get("customer_turns_asr")
        if asr_turns is not None and (not isinstance(asr_turns, list) or any(not isinstance(t, str) or not t.strip() for t in asr_turns)):
            errors.append(f"call {call.get('call_index')}: customer_turns_asr must be a list of non-empty strings")
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
