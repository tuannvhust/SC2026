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
    return "\n".join(t for t in turns if isinstance(t, str)) if isinstance(turns, list) else ""


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
              raw_dir: Path = RAW_DIR) -> list[dict]:
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
    customer = None
    if brief:
        try:
            customer = next((c for c in _read(BTC_DIR / "catalog" / "crm_seed.json")["customers"]
                             if c.get("customer_id") == brief.get("customer_id")), None)
        except Exception:
            pass
        for field, expected in (("persona", brief.get("persona_id")), ("customer_id", brief.get("customer_id")),
                                ("level", brief.get("level", "M1"))):
            if scenario.get(field) != expected:
                _error(rows, sid, "*", "E1_BRIEF_SCENARIO_MISMATCH", f"{field} differs from brief")
        expected_hard = "_".join(brief.get("hard_case_tags", [])) or None
        if scenario.get("hard_case") != expected_hard:
            _error(rows, sid, "*", "E1_HARD_CASE_MISMATCH", "hard_case differs from brief")
        if len(calls) != len(brief.get("calls", [])):
            _error(rows, sid, "*", "E1_CALL_COUNT_MISMATCH", "scenario call count differs from brief")

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
        turns = call.get("customer_turns")
        if not isinstance(turns, list) or not 4 <= len(turns) <= 8 or any(not isinstance(t, str) or not t.strip() for t in turns):
            _error(rows, sid, idx, "E1_TURN_COUNT", "customer_turns must contain 4-8 non-empty customer turns", str(turns))
        elif any(ROLE_LEAK_RE.search(t) for t in turns):
            _error(rows, sid, idx, "E1_AGENT_TEXT_IN_CUSTOMER_TURNS", "customer_turns contains an agent/assistant line", _customer_text(call))

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
            if call.get("call_date") != spec.get("call_date") and spec.get("call_date"):
                _error(rows, sid, idx, "E1_CALL_DATE_MISMATCH", "call_date differs from brief")
            channel = spec.get("channel", brief.get("channel", "hotline"))
            if call.get("channel") != channel:
                _error(rows, sid, idx, "E1_CHANNEL_MISMATCH", "channel differs from brief")
            identity = spec.get("channel_identity") or _expected_channel_identity(customer, channel)
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
                try:
                    if call.get("ground_truth_facts") != derive_ground_truth(pack):
                        _error(rows, sid, idx, "E2_GROUND_TRUTH_MISMATCH", "ground_truth_facts differs from deterministic fact pack")
                    if call.get("success_if") != derive_success_if(spec, pack):
                        _error(rows, sid, idx, "E2_SUCCESS_IF_MISMATCH", "success_if differs from brief/fact pack")
                except Exception as exc:
                    _error(rows, sid, idx, "E2_EXPECTATION_DERIVATION_FAILED", str(exc))

                expected_products = spec.get("products", [])
                packed_products = pack.get("products", [])
                if len(expected_products) != len(packed_products):
                    _error(rows, sid, idx, "E2_PRODUCT_COUNT_MISMATCH", "fact pack product count differs from brief")
                tool = mock_tools()
                for pos, (bp, pp) in enumerate(zip(expected_products, packed_products), 1):
                    sku = bp.get("variant_id") or bp.get("sku")
                    if pp.get("sku") != sku or pp.get("qty", 1) != bp.get("qty", 1):
                        _error(rows, sid, idx, "E2_PRODUCT_FACT_MISMATCH", f"product {pos} SKU/qty differs from brief")
                    if sku not in catalog:
                        _error(rows, sid, idx, "E2_UNKNOWN_SKU", f"brief product SKU not found in catalog: {sku}")
                        continue
                    quote = tool.pricing_get_quote(sku=sku, on=pack.get("call_date"), qty=bp.get("qty", 1),
                                                   customer_phone=(customer or {}).get("phone"), address=spec.get("address"))
                    inventory = tool.inventory_check(sku=sku, on=pack.get("call_date"))
                    if pp.get("quote") != quote:
                        _error(rows, sid, idx, "E2_QUOTE_NOT_FROM_MOCK", f"product {pos} quote differs from reference mock")
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
    args = parser.parse_args()
    rows: list[dict] = []
    for path in sorted(args.scenarios.glob("*.json")):
        rows.extend(check_one(path, args.briefs, args.fact_packs, args.raw))
    try:
        validator = BTC_DIR / "eval" / "validate_scenarios.py"
        if not validator.exists():
            rows.append({"scenario_id": "*", "call_index": "*", "error_code": "W0_BTC_VALIDATOR_MISSING",
                         "description": "Không tìm thấy validator scenario của BTC; các kiểm tra nội bộ không thay thế hoặc khẳng định tương đương validator BTC.",
                         "excerpt": str(validator), "hard": "false"})
    except Exception:
        pass
    REPORTS_DIR.mkdir(exist_ok=True)
    report = REPORTS_DIR / "auto_check_report.csv"
    fields = ["scenario_id", "call_index", "error_code", "description", "excerpt", "hard"]
    with report.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    hard = [r for r in rows if r.get("hard") == "true"]
    print(json.dumps({"scenarios": len(list(args.scenarios.glob('*.json'))), "issues": len(rows),
                      "hard_errors": len(hard), "report": str(report)}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if hard else 0)


if __name__ == "__main__":
    main()
