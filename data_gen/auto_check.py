from __future__ import annotations

"""Deterministic QA for generated customer-only scenarios.

This checks artifact consistency and customer-text safety/grounding. It cannot
score agent behavior: generated scenarios contain customer turns, not responses.
"""

import argparse
import csv
import importlib.util
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .assemble_scenario import derive_ground_truth, derive_success_if
from .config import BRIEFS_DIR, BTC_DIR, FACT_PACKS_DIR, RAW_DIR, REPORTS_DIR
from .facts import extract_policy_chunks, pricing_address_for_call, promotion_evidence
from .scenario_metadata import (
    customer_goal_for_call, hard_case_label, scenario_notes, scenario_summary_path,
)


MONEY_SUFFIX = r"(?:₫|đồng|đ|vnd|triệu|tr(?:iệu)?|nghìn|ngàn|k)"
MONEY_RE = re.compile(
    rf"(?<!\w)(\d{{1,3}}(?:[.,\s]\d{{3}})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*({MONEY_SUFFIX})(?!\w)",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?<!\d)0\d{9}(?!\d)")
CCCD_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
INTERNAL_CODE_RE = re.compile(r"\b(?:NB|NQ)-\d{2,}\b", re.IGNORECASE)
ROLE_LEAK_RE = re.compile(r"(?im)^\s*(?:agent|assistant|nhân viên|tư vấn viên)\s*:")


REPORT_DESCRIPTIONS = {
    "E0_INVALID_SCENARIO_JSON": "Không đọc được JSON của scenario.",
    "E0_ID_FILENAME_MISMATCH": "Mã scenario không khớp tên tệp.",
    "E0_BRIEF_MISSING_OR_INVALID": "Thiếu brief hoặc không đọc được JSON brief.",
    "E0_RAW_INVALID": "Không đọc được JSON lượt khách gốc.",
    "E1_CALLS_INVALID": "Scenario phải có object calls không rỗng.",
    "E1_BRIEF_SCENARIO_MISMATCH": "Thông tin persona/customer_id/level không khớp brief.",
    "E1_HARD_CASE_MISMATCH": "Danh sách hard case không khớp brief.",
    "E1_NOTES_MISMATCH": "Ghi chú scenario không khớp bối cảnh brief.",
    "E1_CUSTOMER_GOAL_MISMATCH": "customer_goal không đúng vị trí hoặc ý nghĩa trong brief.",
    "E1_SCENARIO_SUMMARY_MISSING": "Thiếu summary artifact đã sinh cho notes/customer_goal.",
    "E1_STORY_HINTS_MISMATCH": "story_hints trong scenario metadata không khớp brief.",
    "E1_CALL_COUNT_MISMATCH": "Số cuộc gọi trong scenario không khớp brief.",
    "E1_CALL_KEY_INVALID": "Tên cuộc gọi không đúng định dạng call_N.",
    "E1_CALL_INVALID": "Thông tin cuộc gọi phải là object.",
    "E1_TURN_COUNT": "customer_turns phải có từ 4 đến 8 lượt khách không rỗng.",
    "E1_AGENT_TEXT_IN_CUSTOMER_TURNS": "Lượt khách có chứa lời thoại hoặc nhãn vai của nhân viên/agent.",
    "W1_RAW_MISSING": "Không tìm thấy tệp lượt khách gốc.",
    "E1_RAW_SCENARIO_TURNS_MISMATCH": "Lượt khách trong scenario không khớp dữ liệu sinh gốc.",
    "E1_RAW_METADATA_MISMATCH": "scenario_id trong metadata của dữ liệu gốc không khớp.",
    "E3_PII_LEAK": "Lời khách có thể chứa số điện thoại, CCCD 12 chữ số hoặc email.",
    "E3_INTERNAL_CODE_LEAK": "Lời khách chứa mã nhà cung cấp/chi phí nội bộ.",
    "E1_CALL_DATE_MISMATCH": "Ngày gọi không khớp brief.",
    "E1_CHANNEL_MISMATCH": "Kênh của cuộc gọi không khớp brief.",
    "E1_CHANNEL_IDENTITY_MISMATCH": "Định danh trên kênh không khớp CRM hoặc brief.",
    "E2_FACT_PACK_MISSING_OR_INVALID": "Thiếu fact pack hoặc không đọc được JSON fact pack.",
    "E2_FACT_PACK_ID_MISMATCH": "brief_id/call_index trong fact pack không khớp.",
    "E2_GROUND_TRUTH_MISMATCH": "ground_truth_facts không khớp fact pack xác định bằng code.",
    "E2_SUCCESS_IF_MISMATCH": "success_if không khớp brief và fact pack.",
    "E2_EXPECTATION_DERIVATION_FAILED": "Không thể tính lại điều kiện kỳ vọng từ brief/fact pack.",
    "E2_PRODUCT_COUNT_MISMATCH": "Số sản phẩm trong fact pack không khớp brief.",
    "E2_PRODUCT_FACT_MISMATCH": "SKU hoặc số lượng sản phẩm trong fact pack không khớp brief.",
    "E2_UNKNOWN_SKU": "Không tìm thấy SKU sản phẩm trong catalog.",
    "E2_QUOTE_NOT_FROM_MOCK": "Báo giá trong fact pack khác kết quả mock tool tham chiếu.",
    "E2_INVENTORY_NOT_FROM_MOCK": "Tồn kho trong fact pack khác kết quả mock tool tham chiếu.",
    "E3_INTERNAL_FLOOR_LEAK": "Lời khách có chứa giá sàn nội bộ.",
    "E4_HARDCASE_BASKET": "Ca giỏ hàng vượt ngưỡng cần ít nhất bốn sản phẩm phân biệt.",
    "E4_HARDCASE_CALLBACK": "Brief ca callback ngày nghỉ chưa ghi đúng thời điểm yêu cầu.",
    "E3_UNGROUNDED_MONEY": "Lời khách có số tiền không được hỗ trợ bởi brief/fact pack.",
    "W9_MANUAL_REVIEW": "Cần review thủ công giọng persona, mạch story_hints, tính hợp lý và việc hard case có thực sự xuất hiện.",
}
REPORT_DESCRIPTIONS.update({
    "E2_POLICY_EVIDENCE_MISMATCH": "Policy evidence differs from the requested BTC source chunks.",
    "E2_PROMOTION_REQUEST_MISMATCH": "Promotion codes differ between brief and fact pack.",
    "E2_PROMOTION_EVIDENCE_MISMATCH": "Promotion evidence differs from product, date, CRM region, or mock conditions.",
    "E5_MATRIX_CUSTOMER_MISMATCH": "Primary customer differs between matrix and brief.",
    "E5_MATRIX_REGION_MISMATCH": "Matrix region differs from the primary customer's CRM region.",
    "E5_MATRIX_PROMOTION_MISMATCH": "Brief uses a promotion absent from the matrix row.",
    "E5_MATRIX_POLICY_MISMATCH": "Policy chunk IDs differ between matrix and brief.",
    "E5_CALL_CUSTOMER_REGION_MISMATCH": "Call customer identity/region in fact pack differs from the caller assigned in CRM.",
    "E1_ADDRESS_CONFIRMATION_MISSING": "Address-confirmation call must include the exact CRM address in customer turns.",
})


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE)


def _amount(number: str, suffix: str) -> int:
    raw = number.replace(" ", "")
    suffix = suffix.lower()
    if suffix in {"triệu", "tr", "triệu"}:
        raw = raw.replace(",", ".")
        return round(float(raw) * 1_000_000)
    if suffix in {"k", "nghìn", "ngàn"}:
        raw = raw.replace(",", ".")
        return round(float(raw) * 1_000)
    # Currency values with grouped thousands; decimal separators are accepted
    # only when there is a suffix, e.g. 4,89tr.
    compact = raw.replace(".", "").replace(",", "")
    return int(compact)


def money_values(text: str) -> set[int]:
    values: set[int] = set()
    for match in MONEY_RE.finditer(text):
        try:
            values.add(_amount(match.group(1), match.group(2)))
        except (ValueError, OverflowError):
            continue
    return values


@lru_cache(maxsize=1)
def mock_tools():
    path = BTC_DIR / "eval" / "mock_tools.py"
    spec = importlib.util.spec_from_file_location("btc_mock_tools_autocheck", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load reference mock tools: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_excerpt(text: str, limit: int = 180) -> str:
    text = PHONE_RE.sub("[PHONE]", text)
    text = CCCD_RE.sub("[ID]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    return text.replace("\n", " ")[:limit]


def _customer_text(call: dict) -> str:
    turns = call.get("customer_turns", [])
    asr_turns = call.get("customer_turns_asr", [])
    clean_text = "\n".join(t for t in turns if isinstance(t, str)) if isinstance(turns, list) else ""
    asr_text = "\n".join(t for t in asr_turns if isinstance(t, str)) if isinstance(asr_turns, list) else ""
    return f"{clean_text}\n{asr_text}".strip()


def _ground_truth_matches(call: dict, fact_pack: dict) -> bool:
    """Ground truth must be the complete deterministic projection of its pack."""
    supplied = call.get("ground_truth_facts")
    return isinstance(supplied, dict) and supplied == derive_ground_truth(fact_pack)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_matrix(path: Path, calls_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read the current split coverage files (slot metadata + call assignments).

    Keep the call rows attached to each slot so validation can compare the
    correct customer/promotion/policy assignment for each call. Also expose
    aggregate legacy fields for checks which operate at slot level.
    """
    slots = {
        row.get("slot_id", ""): row
        for row in _read_csv_rows(path)
        if row.get("slot_id")
    }
    if not slots:
        return {}
    assigned_calls: dict[str, list[dict[str, str]]] = {slot_id: [] for slot_id in slots}
    calls_file = calls_path or path.with_name("coverage_calls.csv")
    for row in _read_csv_rows(calls_file):
        slot_id = row.get("slot_id", "")
        if slot_id in assigned_calls:
            assigned_calls[slot_id].append(row)
    for slot_id, slot in slots.items():
        call_rows = assigned_calls[slot_id]
        slot["_calls"] = call_rows
        slot["customer_ids"] = "|".join(dict.fromkeys(r.get("customer_id", "") for r in call_rows if r.get("customer_id")))
        slot["promo_codes_in_play"] = "|".join(dict.fromkeys(r.get("promotion_code", "") for r in call_rows if r.get("promotion_code")))
        slot["policy_chunk_ids"] = "|".join(dict.fromkeys(
            policy.strip()
            for r in call_rows
            for policy in (r.get("policy_chunk_ids", "") or "").split("|")
            if policy.strip()
        ))
    return slots


def _error(rows: list[dict], sid: str, call_index: str, code: str, message: str,
           excerpt: str = "", hard: bool = True) -> None:
    # Exception details may be English or expose local filesystem paths.
    description = REPORT_DESCRIPTIONS.get(code, "Đã phát hiện vấn đề cần kiểm tra.")
    rows.append({
        "scenario_id": sid, "call_index": call_index, "error_code": code,
        "description": description, "excerpt": _safe_excerpt(excerpt), "hard": str(hard).lower(),
    })


def _catalog_facts() -> dict[str, dict]:
    catalog = _read(BTC_DIR / "catalog" / "products.json")["products"]
    result = {}
    for product in catalog:
        result[product["sku"]] = product
        for variant in product.get("variants", []):
            result[variant["variant_sku"]] = product
    return result


def _expected_channel_identity(customer: dict | None, channel: str) -> Any:
    if not customer:
        return None
    key = {"hotline": "phone", "chat_fanpage": "fb_id", "zalo_oa": "zalo_id"}.get(channel)
    return customer.get(key) if key else None


def check_one(path: Path, briefs_dir: Path = BRIEFS_DIR, packs_dir: Path = FACT_PACKS_DIR,
              raw_dir: Path = RAW_DIR, matrix_rows: dict[str, dict[str, str]] | None = None) -> list[dict]:
    rows: list[dict] = []
    try:
        scenario = _read(path)
    except Exception as exc:
        _error(rows, path.stem, "*", "E0_INVALID_SCENARIO_JSON", str(exc))
        return rows
    sid = str(scenario.get("scenario_id") or path.stem)
    if sid != path.stem:
        _error(rows, sid, "*", "E0_ID_FILENAME_MISMATCH", f"scenario_id {sid} differs from filename {path.stem}")

    brief_path = briefs_dir / f"{sid}.json"
    try:
        brief = _read(brief_path)
    except Exception as exc:
        brief = None
        _error(rows, sid, "*", "E0_BRIEF_MISSING_OR_INVALID", str(exc))

    calls = scenario.get("calls")
    if not isinstance(calls, dict) or not calls:
        _error(rows, sid, "*", "E1_CALLS_INVALID", "calls must be a non-empty object")
        calls = {}
    expected_specs = {str(c.get("call_index")): c for c in (brief or {}).get("calls", [])}
    try:
        sidecar = _read(path.parent.with_name(f"{path.parent.name}_metadata") / f"{sid}.json")
    except Exception:
        sidecar = {}
    summary = None
    try:
        summary = _read(scenario_summary_path(raw_dir, sid))
    except Exception:
        _error(rows, sid, "*", "E1_SCENARIO_SUMMARY_MISSING", "scenario metadata summary artifact is missing or invalid")
    customer = None
    if brief:
        try:
            customer = next((c for c in _read(BTC_DIR / "catalog" / "crm_seed.json")["customers"]
                             if c.get("customer_id") == brief.get("customer_id")), None)
        except Exception:
            pass
        for field, expected in (("persona", brief.get("persona_id")),
                                ("level", brief.get("level", "M1"))):
            if scenario.get(field) != expected:
                _error(rows, sid, "*", "E1_BRIEF_SCENARIO_MISMATCH", f"{field} differs from brief")
        expected_hard = hard_case_label(brief.get("hard_case_tags", []))
        if scenario.get("hard_case") != expected_hard:
            _error(rows, sid, "*", "E1_HARD_CASE_MISMATCH", "hard_case differs from brief")
        if not isinstance(summary, dict) or summary.get("scenario_id") != sid:
            _error(rows, sid, "*", "E1_SCENARIO_SUMMARY_MISSING", "scenario metadata summary does not match brief")
        expected_goal = customer_goal_for_call(
            brief,
            next((item for item in brief.get("calls", []) if item.get("call_index") == 1), {}),
        )
        if calls.get("call_1", {}).get("customer_goal") != expected_goal:
            _error(rows, sid, "*", "E1_CUSTOMER_GOAL_MISMATCH", "call_1 customer_goal differs from its brief call story")
        expected_notes = scenario_notes(brief)
        if scenario.get("notes") != expected_notes:
            _error(rows, sid, "*", "E1_SCENARIO_NOTES_MISMATCH", "scenario notes differ from deterministic brief-derived notes")
        expected_story_hints = {
            f"call_{call.get('call_index')}": call.get("story_hint", "")
            for call in brief.get("calls", [])
        }
        if sidecar.get("story_hints") != expected_story_hints:
            _error(rows, sid, "*", "E1_STORY_HINTS_MISMATCH", "scenario metadata story_hints differ from brief")
        if len(calls) != len(brief.get("calls", [])):
            _error(rows, sid, "*", "E1_CALL_COUNT_MISMATCH", "scenario call count differs from brief")
        matrix_row = (matrix_rows or {}).get(sid)
        if matrix_row:
            matrix_customer = matrix_row.get("customer_id")
            if matrix_customer and matrix_customer != brief.get("customer_id"):
                _error(rows, sid, "*", "E5_MATRIX_CUSTOMER_MISMATCH", "matrix primary customer_id differs from brief customer_id")
            if customer and matrix_row.get("mien") and customer.get("region") != matrix_row.get("mien"):
                _error(rows, sid, "*", "E5_MATRIX_REGION_MISMATCH", "matrix mien differs from primary customer's CRM region")
            matrix_promos = {x for x in matrix_row.get("promo_codes_in_play", "").split("|") if x}
            brief_promos = {x for c in brief.get("calls", []) for x in c.get("promo_codes_in_play", [])}
            if matrix_promos != brief_promos:
                _error(rows, sid, "*", "E5_MATRIX_PROMOTION_MISMATCH", "brief and matrix promotion code sets differ", repr({"matrix_only": sorted(matrix_promos - brief_promos), "brief_only": sorted(brief_promos - matrix_promos)}))
            matrix_policy = {x for x in matrix_row.get("policy_chunk_ids", "").split("|") if x}
            brief_policy = {x for c in brief.get("calls", []) for x in c.get("policy_chunk_ids", [])}
            if matrix_policy != brief_policy:
                _error(rows, sid, "*", "E5_MATRIX_POLICY_MISMATCH", "brief policy chunk IDs differ from its matrix row", repr({"matrix": sorted(matrix_policy), "brief": sorted(brief_policy)}))
            # The current coverage format assigns these facts per call. Check
            # each assignment rather than relying only on slot-level unions.
            assigned_by_call = {str(r.get("call_index", "")): r for r in matrix_row.get("_calls", [])}
            for call_spec in brief.get("calls", []):
                call_id = str(call_spec.get("call_index", ""))
                assigned = assigned_by_call.get(call_id)
                if not assigned:
                    continue  # Older, single-file matrices have no call rows.
                assigned_customer = assigned.get("customer_id", "")
                brief_customer = call_spec.get("customer_id", brief.get("customer_id", ""))
                if assigned_customer and assigned_customer != brief_customer:
                    _error(rows, sid, call_id, "E5_MATRIX_CUSTOMER_MISMATCH", "call customer_id differs from coverage_calls assignment", repr({"coverage": assigned_customer, "brief": brief_customer}))
                assigned_promo = {assigned["promotion_code"]} if assigned.get("promotion_code") else set()
                brief_promo = set(call_spec.get("promo_codes_in_play", []))
                if assigned_promo != brief_promo:
                    _error(rows, sid, call_id, "E5_MATRIX_PROMOTION_MISMATCH", "call promotion codes differ from coverage_calls assignment", repr({"coverage": sorted(assigned_promo), "brief": sorted(brief_promo)}))
                assigned_policy = {x.strip() for x in (assigned.get("policy_chunk_ids", "") or "").split("|") if x.strip()}
                brief_call_policy = set(call_spec.get("policy_chunk_ids", []))
                if assigned_policy != brief_call_policy:
                    _error(rows, sid, call_id, "E5_MATRIX_POLICY_MISMATCH", "call policy chunk IDs differ from coverage_calls assignment", repr({"coverage": sorted(assigned_policy), "brief": sorted(brief_call_policy)}))
            promo_catalog = _read(BTC_DIR / "catalog" / "promotions.json").get("promotions", [])
            promo_by_code = {item.get("promo_code"): item for item in promo_catalog}
            product_catalog = _catalog_facts()
            for call_spec in brief.get("calls", []):
                call_id = str(call_spec.get("call_index"))
                caller_id = call_spec.get("customer_id", brief.get("customer_id"))
                caller = next((item for item in _read(BTC_DIR / "catalog" / "crm_seed.json")["customers"] if item.get("customer_id") == caller_id), None)
                region = (caller or {}).get("region")
                sku_set = {p.get("variant_id") or p.get("sku") for p in call_spec.get("products", [])}
                for code in call_spec.get("promo_codes_in_play", []):
                    promo = promo_by_code.get(code)
                    if not promo:
                        _error(rows, sid, call_id, "E5_UNKNOWN_PROMOTION", f"unknown promotion code: {code}")
                        continue
                    targets = promo.get("applies_to", [])
                    applicable = any(
                        "*" in targets
                        or sku in targets
                        or product_catalog.get(sku, {}).get("sku") in targets
                        or any(t.startswith("category:") and product_catalog.get(sku, {}).get("category", "").startswith(t.split(":", 1)[1]) for t in targets)
                        for sku in sku_set
                    )
                    # A future offer is a timing trap; its category condition
                    # is still checked as a separate policy fact, not treated
                    # as an applied quote for an unrelated product.
                    if not applicable and code != "11-11" and matrix_row.get("hard_case_tag") not in {"promo_expired", "promo_condition_fail"}:
                        _error(rows, sid, call_id, "E5_PROMOTION_PRODUCT_MISMATCH", f"{code} does not apply to products {sorted(sku_set)}")
                    allowed_regions = promo.get("conditions", {}).get("region")
                    if allowed_regions and region not in allowed_regions and matrix_row.get("hard_case_tag") != "promo_condition_fail":
                        _error(rows, sid, call_id, "E5_PROMOTION_REGION_MISMATCH", f"{code} region condition {allowed_regions} does not match caller region {region}")
                if matrix_row.get("hard_case_tag") in {"promo_expired", "promo_not_started", "promo_condition_fail", "size_excluded_promotion"} and not call_spec.get("promo_codes_in_play"):
                    _error(rows, sid, call_id, "E5_HARD_CASE_PROMOTION_MISSING", "promotion hard case has no promotion code assigned")
            for code in matrix_policy:
                if code.startswith("CL-"):
                    _error(rows, sid, "*", "E5_CHANGELOG_AS_POLICY", f"{code} is a changelog ID, not an operational policy chunk")

    try:
        catalog = _catalog_facts()
    except Exception:
        catalog = {}
    used_numbers: set[int] = set()
    allowed_numbers: set[int] = set()
    for call_name, call in calls.items():
        match = re.fullmatch(r"call_(\d+)", str(call_name))
        idx = match.group(1) if match else "?"
        spec = expected_specs.get(idx)
        if not match:
            _error(rows, sid, idx, "E1_CALL_KEY_INVALID", f"invalid call key: {call_name}")
        if not isinstance(call, dict):
            _error(rows, sid, idx, "E1_CALL_INVALID", "call must be an object")
            continue
        if spec:
            if idx != "1" and "customer_goal" in call:
                _error(rows, sid, idx, "E1_CUSTOMER_GOAL_MISMATCH", "customer_goal belongs on call_1 only")
        turns = call.get("customer_turns")
        if not isinstance(turns, list) or not 4 <= len(turns) <= 8 or any(not isinstance(t, str) or not t.strip() for t in turns):
            _error(rows, sid, idx, "E1_TURN_COUNT", "customer_turns must contain 4-8 non-empty customer turns", str(turns))
        elif any(ROLE_LEAK_RE.search(t) for t in turns):
            _error(rows, sid, idx, "E1_AGENT_TEXT_IN_CUSTOMER_TURNS", "customer_turns contains an agent/assistant line", _customer_text(call))
        facts_established = call.get("facts_established", {})
        address = facts_established.get("customer_address_to_confirm") if isinstance(facts_established, dict) else None
        if isinstance(facts_established, dict) and facts_established.get("address_confirmed") is True:
            if not address or not isinstance(turns, list) or address not in " ".join(turns):
                _error(rows, sid, idx, "E1_ADDRESS_CONFIRMATION_MISSING", "address_confirmed requires the exact delivery address in customer turns")
        asr_turns = call.get("customer_turns_asr")
        if call.get("input_mode", "clean") != "clean" and (
            not isinstance(asr_turns, list)
            or len(asr_turns) != (len(turns) if isinstance(turns, list) else -1)
            or any(not isinstance(t, str) or not t.strip() for t in asr_turns)
        ):
            _error(rows, sid, idx, "E1_ASR_TURN_CONTRACT", "customer_turns_asr must match clean turn count and contain non-empty strings")

        raw_path = raw_dir / f"{sid}_c{idx}.json"
        if not raw_path.exists():
            _error(rows, sid, idx, "W1_RAW_MISSING", f"raw generation artifact not found: {raw_path.name}", hard=False)
        else:
            try:
                raw = _read(raw_path)
                raw_turns = raw.get("customer_turns")
                if raw_turns is None:
                    raw_turns = [x.get("text") for x in raw.get("dialogue", []) if x.get("role") == "customer"]
                if raw_turns != turns:
                    _error(rows, sid, idx, "E1_RAW_SCENARIO_TURNS_MISMATCH", "scenario turns differ from raw generated turns")
                raw_asr_turns = raw.get("customer_turns_asr")
                if asr_turns is not None and raw_asr_turns is not None and raw_asr_turns != asr_turns:
                    _error(rows, sid, idx, "E1_RAW_SCENARIO_ASR_MISMATCH", "scenario ASR turns differ from raw generated turns")
                meta = raw.get("generation_meta", {})
                if meta.get("scenario_id") and meta["scenario_id"] != sid:
                    _error(rows, sid, idx, "E1_RAW_METADATA_MISMATCH", "raw artifact scenario_id differs")
            except Exception as exc:
                _error(rows, sid, idx, "E0_RAW_INVALID", str(exc))

        text = _customer_text(call)
        leaked = PHONE_RE.search(text) or CCCD_RE.search(text) or EMAIL_RE.search(text)
        if leaked:
            _error(rows, sid, idx, "E3_PII_LEAK", "customer transcript contains phone, 12-digit ID, or email", text)
        if INTERNAL_CODE_RE.search(text):
            _error(rows, sid, idx, "E3_INTERNAL_CODE_LEAK", "customer transcript contains internal supplier/cost code", text)

        nums = money_values(text)
        used_numbers |= nums
        if spec:
            call_customer_id = spec.get("customer_id", brief.get("customer_id"))
            call_customer = None
            if call_customer_id:
                try:
                    call_customer = next((c for c in _read(BTC_DIR / "catalog" / "crm_seed.json")["customers"]
                                          if c.get("customer_id") == call_customer_id), None)
                except Exception:
                    pass
            recorded_customer_id = sidecar.get("call_customer_ids", {}).get(f"call_{idx}")
            if recorded_customer_id and recorded_customer_id != call_customer_id:
                _error(rows, sid, idx, "E1_CALL_CUSTOMER_MISMATCH", "call customer_id differs from brief caller")
            if call.get("call_date") != spec.get("call_date") and spec.get("call_date"):
                _error(rows, sid, idx, "E1_CALL_DATE_MISMATCH", "call_date differs from brief")
            channel = spec.get("channel", brief.get("channel", "hotline"))
            if call.get("channel") != channel:
                _error(rows, sid, idx, "E1_CHANNEL_MISMATCH", "channel differs from brief")
            identity = spec.get("channel_identity") or _expected_channel_identity(call_customer or customer, channel)
            if identity and call.get("channel_identity") != identity:
                _error(rows, sid, idx, "E1_CHANNEL_IDENTITY_MISMATCH", "channel_identity differs from CRM/brief")
            try:
                pack = _read(packs_dir / f"{sid}_c{idx}.json")
            except Exception as exc:
                pack = None
                _error(rows, sid, idx, "E2_FACT_PACK_MISSING_OR_INVALID", str(exc))
            if pack:
                if pack.get("brief_id") != sid or str(pack.get("call_index")) != idx:
                    _error(rows, sid, idx, "E2_FACT_PACK_ID_MISMATCH", "fact pack brief/call ID mismatch")
                packed_customer = pack.get("customer", {})
                packed_crm = packed_customer.get("crm", {}) if isinstance(packed_customer, dict) else {}
                if not isinstance(packed_customer, dict) or packed_customer.get("customer_id") != call_customer_id or packed_crm.get("region") != (call_customer or {}).get("region"):
                    _error(rows, sid, idx, "E5_CALL_CUSTOMER_REGION_MISMATCH", "fact pack caller ID/region differs from the call's CRM customer")
                requested_policy = list(spec.get("policy_chunk_ids", []))
                packed_policy = list(pack.get("requested_policy_chunk_ids", []))
                actual_policy = {p.get("chunk_id") for p in pack.get("policy", [])} | set(pack.get("internal_policy_ids", []))
                if requested_policy != packed_policy or set(requested_policy) != actual_policy:
                    _error(rows, sid, idx, "E2_POLICY_EVIDENCE_MISMATCH", "policy IDs in brief, fact pack request, and extracted policy evidence differ",
                           repr({"brief": requested_policy, "pack_requested": packed_policy, "extracted": sorted(actual_policy)}))
                source_policy = extract_policy_chunks(requested_policy)
                source_public = [p for p in source_policy if p["type"] != "internal"]
                source_internal_ids = [p["chunk_id"] for p in source_policy if p["type"] == "internal"]
                if pack.get("policy") != source_public or set(pack.get("internal_policy_ids", [])) != set(source_internal_ids):
                    _error(rows, sid, idx, "E2_POLICY_EVIDENCE_MISMATCH", "fact pack policy content/type does not match selected BTC source chunks")
                requested_promos = list(spec.get("promo_codes_in_play", []))
                if requested_promos != list(pack.get("promo_codes_in_play", [])):
                    _error(rows, sid, idx, "E2_PROMOTION_REQUEST_MISMATCH", "promotion codes in fact pack differ from brief")
                try:
                    if not _ground_truth_matches(call, pack):
                        _error(rows, sid, idx, "E2_GROUND_TRUTH_MISMATCH", "a supplied ground_truth_facts assertion differs from the deterministic fact pack")
                    if call.get("success_if") != derive_success_if(spec, pack):
                        _error(rows, sid, idx, "E2_SUCCESS_IF_MISMATCH", "success_if differs from brief/fact pack")
                except Exception as exc:
                    _error(rows, sid, idx, "E2_EXPECTATION_DERIVATION_FAILED", str(exc))

                expected_products = spec.get("products", [])
                packed_products = pack.get("products", [])
                if len(expected_products) != len(packed_products):
                    _error(rows, sid, idx, "E2_PRODUCT_COUNT_MISMATCH", "fact pack product count differs from brief")
                tool = mock_tools()
                basket_skus = [p.get("variant_id") or p.get("sku") for p in expected_products]
                pricing_address = pricing_address_for_call(spec, customer)
                for product_index, (bp, pp) in enumerate(zip(expected_products, packed_products)):
                    pos = product_index + 1
                    sku = bp.get("variant_id") or bp.get("sku")
                    if pp.get("sku") != sku or pp.get("qty", 1) != bp.get("qty", 1):
                        _error(rows, sid, idx, "E2_PRODUCT_FACT_MISMATCH", f"product {pos} SKU/qty differs from brief")
                    if sku not in catalog:
                        _error(rows, sid, idx, "E2_UNKNOWN_SKU", f"brief product SKU not found in catalog: {sku}")
                        continue
                    quote = tool.pricing_get_quote(sku=sku, on=pack.get("call_date"), qty=bp.get("qty", 1),
                                                   customer_phone=(customer or {}).get("phone"), address=pricing_address,
                                                   basket_skus=[item for i, item in enumerate(basket_skus) if i != product_index])
                    inventory = tool.inventory_check(sku=sku, on=pack.get("call_date"))
                    if pp.get("quote") != quote:
                        _error(rows, sid, idx, "E2_QUOTE_NOT_FROM_MOCK", f"product {pos} quote differs from reference mock")
                    evidence_codes = list(dict.fromkeys([
                        *requested_promos,
                        *(p["promo_code"] for p in quote.get("applied_promos", [])),
                        *quote.get("expired_promos", []),
                        *(p["promo_code"] for p in quote.get("ineligible_promos", [])),
                        *quote.get("not_applied_exclusive", []),
                    ]))
                    expected_promotion_evidence = promotion_evidence(evidence_codes, sku, quote, pack.get("call_date"))
                    if pp.get("promotion_evidence") != expected_promotion_evidence:
                        _error(rows, sid, idx, "E2_PROMOTION_EVIDENCE_MISMATCH", f"product {pos} promotion evidence differs from mock quote/catalog conditions")
                    if pp.get("inventory") != inventory:
                        _error(rows, sid, idx, "E2_INVENTORY_NOT_FROM_MOCK", f"product {pos} inventory differs from reference mock")
                    allowed_numbers.update(v for v in (quote.get("list_price_vnd"), quote.get("final_price_vnd")) if isinstance(v, int))
                    floor = quote.get("_internal_price_floor_vnd")
                    if isinstance(floor, int) and floor in nums:
                        _error(rows, sid, idx, "E3_INTERNAL_FLOOR_LEAK", "customer transcript contains an internal price floor", text)
                facts = pack.get("customer_facts", {})
                if isinstance(facts, dict):
                    allowed_numbers.update(v for v in facts.values() if isinstance(v, int) and not isinstance(v, bool))
            for key, value in (spec.get("facts_to_establish") or {}).items():
                if isinstance(value, int) and not isinstance(value, bool) and key.endswith(("_vnd", "_price")):
                    allowed_numbers.add(value)
        else:
            pack = None

        tags = set((brief or {}).get("hard_case_tags", []))
        if "multi_product_cod_budget" in tags and spec:
            products = spec.get("products", [])
            distinct = {p.get("variant_id") or p.get("sku") for p in products}
            if len(distinct) < 4:
                _error(rows, sid, idx, "E4_HARDCASE_BASKET", "multi_product_cod_budget requires four distinct products")
        if "callback_holiday" in tags and spec:
            req = (spec.get("facts_to_establish") or {}).get("callback_requested_at")
            if req != "2026-10-26T09:00":
                _error(rows, sid, idx, "E4_HARDCASE_CALLBACK", "callback_holiday brief must encode the specified holiday request")

    unexpected = used_numbers - allowed_numbers
    if unexpected:
        _error(rows, sid, "*", "E3_UNGROUNDED_MONEY", f"customer transcript contains unsupported money amount(s): {sorted(unexpected)}",
               " ".join(_customer_text(c) for c in calls.values() if isinstance(c, dict)))
    _error(rows, sid, "*", "W9_MANUAL_REVIEW", "Review persona voice, story_hints, plausibility, and whether the intended hard case is actually elicited.", hard=False)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic QA for generated customer-only scenario data")
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--briefs", type=Path, default=BRIEFS_DIR)
    parser.add_argument("--fact-packs", type=Path, default=FACT_PACKS_DIR)
    parser.add_argument("--raw", type=Path, default=RAW_DIR)
    parser.add_argument("--matrix", type=Path, default=REPORTS_DIR / "coverage_matrix.csv")
    parser.add_argument("--calls", type=Path, default=None,
                        help="Per-call coverage CSV; defaults to coverage_calls.csv beside --matrix")
    parser.add_argument("--report", type=Path, default=REPORTS_DIR / "auto_check_report.csv")
    args = parser.parse_args()
    rows: list[dict] = []
    matrix_rows = _read_matrix(args.matrix, args.calls)
    scenario_paths = sorted(args.scenarios.glob("*.json"))
    checked_paths = []
    orphan_count = 0
    for path in scenario_paths:
        if not (args.briefs / path.name).exists():
            orphan_count += 1
            rows.append({"scenario_id": path.stem, "call_index": "*", "error_code": "W0_ORPHAN_SCENARIO",
                         "description": "Scenario has no matching source brief and is excluded from dataset acceptance.",
                         "excerpt": path.name, "hard": "false"})
            continue
        checked_paths.append(path)
        rows.extend(check_one(path, args.briefs, args.fact_packs, args.raw, matrix_rows))
    try:
        validator = BTC_DIR / "eval" / "validate_scenarios.py"
        if not validator.exists():
            rows.append({"scenario_id": "*", "call_index": "*", "error_code": "W0_BTC_VALIDATOR_MISSING",
                         "description": "Không tìm thấy validator scenario của BTC; các kiểm tra nội bộ không thay thế hoặc khẳng định tương đương validator BTC.",
                         "excerpt": str(validator), "hard": "false"})
    except Exception:
        pass
    REPORTS_DIR.mkdir(exist_ok=True)
    report = args.report
    report.parent.mkdir(parents=True, exist_ok=True)
    fields = ["scenario_id", "call_index", "error_code", "description", "excerpt", "hard"]
    with report.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    hard = [r for r in rows if r.get("hard") == "true"]
    print(json.dumps({"scenarios": len(checked_paths), "orphan_scenarios_excluded": orphan_count, "issues": len(rows),
                      "hard_errors": len(hard), "report": str(report)}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if hard else 0)


if __name__ == "__main__":
    main()
