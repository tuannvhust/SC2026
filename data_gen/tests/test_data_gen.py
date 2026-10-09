from __future__ import annotations

import json
from pathlib import Path

from data_gen import auto_check
from data_gen.facts import build_fact_pack
from data_gen.lint_briefs import btc_data, lint_one


ROOT = Path(__file__).resolve().parents[2]


def brief(name="SC-DEMO-01"):
    return json.loads((ROOT / "data_gen" / "briefs" / f"{name}.json").read_text(encoding="utf-8"))


def test_facts_match_mock_for_conditional_promo():
    pack = build_fact_pack(brief("SC-DEMO-01"), 1); product = pack["products"][0]
    assert product["quote"]["final_price_vnd"] == 7590000
    assert any(x["promo_code"] == "TRADE-IN-AP" for x in product["quote"]["applied_promos"])


def test_facts_match_mock_for_expired_promo():
    pack = build_fact_pack(brief("SC-DEMO-02"), 2); quote = pack["products"][0]["quote"]
    assert "AP-SEP" in quote["expired_promos"]


def test_facts_match_inventory_change_by_date():
    b = brief("SC-DEMO-01"); b["calls"][0]["products"][0]["sku"] = "SKU-XM-4P"
    p1 = build_fact_pack(b, 1)["products"][0]["inventory"]
    b["calls"][0]["call_date"] = "2026-10-20"
    p2 = build_fact_pack(b, 1)["products"][0]["inventory"]
    assert p1["in_stock"] is False and p2["in_stock"] is True


def test_lint_catches_five_invalid_types():
    ref = btc_data(); b = brief()
    cases = []
    x = json.loads(json.dumps(b)); x["persona_id"] = "missing"; cases.append(x)
    x = json.loads(json.dumps(b)); x["customer_id"] = "C-MISSING"; cases.append(x)
    x = json.loads(json.dumps(b)); x["calls"][1]["days_later"] = -1; cases.append(x)
    x = json.loads(json.dumps(b)); x["calls"][0]["products"][0]["sku"] = "MISSING"; cases.append(x)
    x = json.loads(json.dumps(b)); x["calls"][0]["facts_to_establish"]["price_vnd"] = 1; cases.append(x)
    assert all(lint_one(Path("memory.json"), ref) for _ in []) is True
    # lint_one reads a path; write small temporary files beside the test module.
    for i, item in enumerate(cases):
        path = ROOT / "data_gen" / "tests" / f"_invalid_{i}.json"; path.write_text(json.dumps(item), encoding="utf-8")
        try: assert lint_one(path, ref)
        finally: path.unlink()


def test_autocheck_catches_four_error_families():
    assert auto_check.money_values("Giá 9.999.000đ và 4,89tr") == {9999000, 4890000}
    assert auto_check.re.search(r"(?<!\d)0\d{9}(?!\d)", "gọi 0984726714")
    assert len(auto_check.words("Dạ giá 4.890.000đ ạ")) >= 3
    assert "room_area_m2" in json.loads((ROOT / "data_gen/slot_keywords.json").read_text(encoding="utf-8"))


def test_generated_scenarios_are_idempotent_inputs():
    first = json.loads((ROOT / "data_gen/scenarios_dryrun/SC-DEMO-01.json").read_text(encoding="utf-8"))
    second = json.loads((ROOT / "data_gen/scenarios_dryrun/SC-DEMO-01.json").read_text(encoding="utf-8"))
    assert first == second
