"""Standalone CallBrief inspection (no Groq, no network).

Run: python scripts/test_call_brief.py
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import AIMessage, HumanMessage

from src.graph.nodes import input_nodes


class _FakePostgresStore:
    def get_session_events(self, _session_id):
        return []

    def get_recent_episodes(self, _customer_id):
        return []


class _FakeProfileStore:
    def get_profile_facts(self, _customer_id):
        return {"name": "An"}


def _mask_phone(phone):
    digits = str(phone or "")
    if len(digits) == 10 and digits.startswith("0"):
        return f"{digits[:3]}***{digits[-4:]}"
    return phone or "none"


def main():
    input_nodes.get_postgres_memory_store = lambda: _FakePostgresStore()
    input_nodes.get_profile_store = lambda: _FakeProfileStore()

    state = {
        "customer_id": "CUST-1029",
        "customer_info": {
            "phone": "0912345678",
            "name": "An",
            "channel": "web_chat",
            "_input_text": "tu van mau so 2",
        },
        "pending_need": "minh muon mua may loc khong khi phong 30m2 gia duoi 10 trieu",
        "messages": [
            HumanMessage(
                content="minh muon mua may loc khong khi phong 30m2 gia duoi 10 trieu"
            ),
            AIMessage(content="Cho em xin ten + SDT a?"),
            HumanMessage(content="tu van mau so 2"),
        ],
        "session_id": "test-brief-01",
    }

    print("=== BUILD CALL BRIEF TEST ===")
    print("[NODE] build_call_brief_node: running")
    print("[INPUT] customer_id: CUST-1029")
    print("[INPUT] customer_name: An")
    print("[INPUT] customer_phone: 091***5678")
    print("[INPUT] pending_need: minh muon mua may loc khong khi phong 30m2")
    print("[INPUT] current_message: tu van mau so 2")

    failures = []
    try:
        result = input_nodes.build_call_brief_node(state)
    except Exception as error:
        print(f"[FAIL] node raised: {error}")
        return 1
    brief = (result or {}).get("call_brief")
    if not isinstance(brief, dict):
        print("[FAIL] node did not return state['call_brief'] dict")
        return 1

    logged = dict(brief)
    if logged.get("customer_phone"):
        logged["customer_phone"] = _mask_phone(logged["customer_phone"])
    print("[OUTPUT]")
    print(json.dumps(logged, ensure_ascii=False, indent=2))

    def check(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail and not ok else ''}")
        if not ok:
            failures.append(name)

    check("customer_id == CUST-1029", brief.get("customer_id") == "CUST-1029")
    check("customer_name == An", brief.get("customer_name") == "An")
    check("customer_phone == 0912345678", brief.get("customer_phone") == "0912345678")
    check("current_need kept", "may loc" in str(brief.get("current_need") or ""))
    check("constraints room 30m2", str(brief.get("constraints", {}).get("room_area_m2")) == "30.0")
    check("budget under 10tr", brief.get("constraints", {}).get("budget_hint_vnd") == 10_000_000)
    check("sample_no == 2", brief.get("constraints", {}).get("sample_no") == 2)
    check(
        "interested_sku == SKU-AP-Y",
        brief.get("constraints", {}).get("interested_sku") == "SKU-AP-Y",
    )
    check("session_id in brief", brief.get("session_id") == "test-brief-01")
    check("profile name An", (brief.get("profile_facts") or {}).get("name") == "An")
    check("suggested_opening has An", "An" in str(brief.get("suggested_opening") or ""))
    check("not messages copy", brief != state["messages"])
    for field in ("customer_phone", "is_returning", "suggested_opening", "generated_at"):
        check(f"required field {field}", field in brief)

    if failures:
        print(f"RESULT: FAIL ({len(failures)} checks)")
        return 1
    print("RESULT: PASS (all checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
