import re
from typing import List, Set

from .state import CallState

_MONEY_FULL = re.compile(r"\d{1,3}(?:\.\d{3})+")  # 4.890.000
_MONEY_TR = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:tr\b|triệu)", re.I)  # 4,89tr / 5 triệu


def extract_money(text: str) -> List[int]:
    """Trích xuất danh sách các giá trị tiền số nguyên từ văn bản tiếng Việt."""
    vals = [int(s.replace(".", "")) for s in _MONEY_FULL.findall(text)]
    vals += [int(round(float(s.replace(",", ".")) * 1_000_000)) for s in _MONEY_TR.findall(text)]
    return vals


def ints_in(obj) -> Set[int]:
    """Đệ quy lấy toàn bộ các số nguyên có trong dict/list dữ liệu trả về từ tool."""
    if isinstance(obj, bool):
        return set()
    if isinstance(obj, int):
        return {obj}
    if isinstance(obj, dict):
        return set().union(*[ints_in(v) for v in obj.values()]) if obj else set()
    if isinstance(obj, list):
        return set().union(*[ints_in(v) for v in obj]) if obj else set()
    return set()


def guardrail_check(state: CallState) -> CallState:
    """Validate money grounding and BTC safety patterns before trace emission."""
    draft = state.get("draft_response")
    if not draft:
        return {"guardrail_passed": False, "guardrail_violation_reason": "no_draft"}
    blob = draft + " " + str(state.get("memory_writes", []))
    if re.search(r"giá nhập|nhà cung cấp|supplier|import_price|_internal_price_floor", blob, re.I):
        return {"guardrail_passed": False, "guardrail_violation_reason": "internal_information"}
    if re.search(r"tôi là (người|nhân viên) thật", draft, re.I):
        return {"guardrail_passed": False, "guardrail_violation_reason": "claims_human"}
    for m in re.finditer(r"\b\d{10,14}\b", blob):
        if not (len(m.group()) == 10 and m.group().startswith("0")):
            return {"guardrail_passed": False, "guardrail_violation_reason": "pii_detected"}
    allowed = ints_in([t["result"] for t in state.get("tool_results", [])])
    bad = [m for m in extract_money(draft) if m not in allowed]
    if bad:
        return {
            "guardrail_passed": False,
            "guardrail_violation_reason": f"money not backed by tool: {bad}, allowed: {sorted(allowed)}",
        }
    return {"guardrail_passed": True, "guardrail_violation_reason": None}
