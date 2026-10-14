from __future__ import annotations

import json
import tempfile
from pathlib import Path

from data_gen import auto_check
from data_gen.auto_check import check_one
from data_gen.assemble_scenario import assemble_scenario
from data_gen.facts import build_fact_pack
from data_gen.lint_briefs import btc_data, lint_one
from data_gen.run_batch import raw_requires_regeneration
from data_gen.gen_dialogue import generation_payload, generation_prompt, parse_customer_turns
from data_gen.coverage_matrix.make_coverage_matrix import _brief_for_row, _products_for_industry
from data_gen.pipeline import validate_btc_contracts, validate_scenario_contract


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


def test_autocheck_checks_turn_contract_and_does_not_treat_measurements_as_money():
    assert auto_check.money_values("phòng 25m2, giao 7 ngày, giá 4,89tr") == {4890000}
    b = brief("SC-DEMO-01")
    packs = {c["call_index"]: build_fact_pack(b, c["call_index"]) for c in b["calls"]}
    raw = {c["call_index"]: {"customer_turns": ["Tôi muốn hỏi thêm.", "Nhà tôi đang cần tư vấn.", "Tôi đang cân nhắc.", "Để tôi xem lại."]} for c in b["calls"]}
    scenario = assemble_scenario(b, raw, packs)
    scenario["calls"]["call_1"]["customer_turns"] = ["Chỉ có ba lượt", "Lượt hai", "Lượt ba"]
    with tempfile.TemporaryDirectory(dir=ROOT / "data_gen" / "tests") as temp:
        tmp_path = Path(temp)
        scenario_dir = tmp_path / "scenarios"; scenario_dir.mkdir()
        brief_dir = tmp_path / "briefs"; brief_dir.mkdir()
        pack_dir = tmp_path / "packs"; pack_dir.mkdir()
        raw_dir = tmp_path / "raw"; raw_dir.mkdir()
        scenario_path = scenario_dir / f'{b["brief_id"]}.json'
        scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
        (brief_dir / f'{b["brief_id"]}.json').write_text(json.dumps(b), encoding="utf-8")
        for index, pack in packs.items():
            (pack_dir / f'{b["brief_id"]}_c{index}.json').write_text(json.dumps(pack), encoding="utf-8")
            (raw_dir / f'{b["brief_id"]}_c{index}.json').write_text(json.dumps(raw[index]), encoding="utf-8")
        findings = check_one(scenario_path, brief_dir, pack_dir, raw_dir)
    assert any(item["error_code"] == "E1_TURN_COUNT" for item in findings)
    assert any(item["error_code"] == "E1_RAW_SCENARIO_TURNS_MISMATCH" for item in findings)


def test_autocheck_validates_generated_artifacts_without_agent_response():
    b = brief("SC-DEMO-01")
    packs = {c["call_index"]: build_fact_pack(b, c["call_index"]) for c in b["calls"]}
    turns = ["Tôi muốn hỏi thêm.", "Nhà tôi đang cần tư vấn.", "Tôi đang cân nhắc.", "Để tôi xem lại."]
    raw = {c["call_index"]: {"customer_turns": turns} for c in b["calls"]}
    scenario = assemble_scenario(b, raw, packs)
    with tempfile.TemporaryDirectory(dir=ROOT / "data_gen" / "tests") as temp:
        tmp_path = Path(temp)
        dirs = [tmp_path / name for name in ("scenarios", "briefs", "packs", "raw")]
        for directory in dirs: directory.mkdir()
        path = dirs[0] / f'{b["brief_id"]}.json'
        path.write_text(json.dumps(scenario), encoding="utf-8")
        (dirs[1] / f'{b["brief_id"]}.json').write_text(json.dumps(b), encoding="utf-8")
        for index, pack in packs.items():
            (dirs[2] / f'{b["brief_id"]}_c{index}.json').write_text(json.dumps(pack), encoding="utf-8")
            (dirs[3] / f'{b["brief_id"]}_c{index}.json').write_text(json.dumps(raw[index]), encoding="utf-8")
        findings = check_one(path, dirs[1], dirs[2], dirs[3])
    assert not [item for item in findings if item["hard"] == "true"]
    assert any(item["error_code"] == "W9_MANUAL_REVIEW" for item in findings)


def test_customer_turn_output_contract():
    assert parse_customer_turns('["Lượt khách một", "Lượt khách hai", "Lượt khách ba", "Lượt khách bốn"]') == [
        "Lượt khách một", "Lượt khách hai", "Lượt khách ba", "Lượt khách bốn"
    ]
    assert len(parse_customer_turns('["1", "2", "3", "4", "5", "6", "7", "8"]')) == 8
    for invalid in ('[{"role":"customer","text":"x"}]', '["chỉ có một lượt"]'):
        try:
            parse_customer_turns(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid customer turn payload was accepted")


def test_persona_system_prompt_is_used_and_fingerprinted():
    call = {"call_index": 2, "customer_goal": "goal sentinel", "facts_to_establish": {"budget_vnd": 8_000_000}, "story_hint": "outline sentinel"}
    system, digest = generation_prompt("khach_so_gia", call, scenario_num_calls=3)
    assert "goal sentinel" in system and "outline sentinel" in system
    assert "Never return 0-3 items" in system
    assert "count is between 4 and 8" in system
    assert "Style: thực dụng, nhắc giá đối thủ, đòi giảm" in system
    assert "Vị trí cuộc gọi: 2/3" in system
    assert "Patience ban đầu của cuộc gọi: 3" in system
    assert "thực dụng" in system or "thá»±c dá»¥ng" in system
    changed_system, changed_digest = generation_prompt("khach_so_gia", {**call, "customer_goal": "different goal"}, scenario_num_calls=3)
    assert changed_system != system and changed_digest != digest
    _, count_changed_digest = generation_prompt("khach_so_gia", call, scenario_num_calls=2)
    assert count_changed_digest != digest


def test_generation_payload_includes_call_count_and_patience():
    scenario = {
        "persona_id": "khach_so_gia",
        "channel": "hotline",
        "calls": [
            {"call_index": 1, "customer_goal": "goal 1"},
            {"call_index": 2, "customer_goal": "goal 2", "channel": "zalo_oa"},
            {"call_index": 3, "customer_goal": "goal 3"},
        ],
    }
    payload = generation_payload(scenario, 2)
    assert payload["scenario_num_calls"] == 3
    assert payload["call_index"] == 2
    assert payload["persona"]["style"] == "thực dụng, nhắc giá đối thủ, đòi giảm"
    assert payload["persona"]["patience_initial"] == 3
    assert payload["channel"] == "zalo_oa"


def test_hard_case_brief_builder_encodes_callback_channels_basket_and_stock():
    from data_gen.coverage_matrix.make_coverage_matrix import load_json

    customers = load_json("catalog/crm_seed.json")["customers"]
    customer = next(c for c in customers if c["customer_id"] == "C034")
    products_all = load_json("catalog/products.json")["products"]
    grouped = {}
    for product in products_all:
        if not product.get("discontinued"):
            grouped.setdefault(product["category"].split("/", 1)[0], []).append(product)
    multi_industry = next(
        industry for industry, items in grouped.items()
        if sum(p.get("list_price_vnd", 0) for p in sorted(items, key=lambda p: p.get("list_price_vnd", 0), reverse=True)[:4]) > 10_000_000
    )

    def make(tag, industry="thoi-trang", calls=2, pattern="hotline-zalo_oa"):
        row = {
            "slot_id": "SC-TEST", "level": "M1", "case_number": "1", "layer": "A",
            "persona_id": "khach_so_gia", "nganh": industry, "mien": "bac",
            "num_calls": str(calls), "channel_pattern": pattern, "hard_case_tag": tag,
            "special_customer": "shared_phone" if tag == "shared_phone" else "none",
            "promo_codes_in_play": "RUN-10", "promo_situation": "conditional",
            "policy_chunk_ids": "DT-01", "policy_situation": "current", "customer_id": customer["customer_id"],
            "story_hints": "Call 1: Nêu nhu cầu ban đầu. || Call 2: Hỏi tiếp kết quả đã trao đổi.",
        }
        return _brief_for_row(row, customer, _products_for_industry(industry))

    callback = make("callback_holiday")
    assert callback["calls"][0]["success_if"] == {"tool_called": "schedule.callback", "args_match": {"callback_at": "2026-10-26T09:00"}}
    assert callback["calls"][0]["facts_to_establish"]["callback_requested_at"] == "2026-10-26T09:00"
    assert callback["calls"][0]["story_hint"] == "Nêu nhu cầu ban đầu."
    assert callback["calls"][1]["story_hint"] == "Hỏi tiếp kết quả đã trao đổi."
    channels = make("three_channel_price_conflict", calls=3)["calls"]
    assert {call["channel"] for call in channels} == {"hotline", "zalo_oa", "chat_fanpage"}
    basket = make("multi_product_cod_budget", industry=multi_industry)
    assert len({p["sku"] for p in basket["calls"][0]["products"]}) == 4
    assert basket["calls"][0]["success_if"]["tool_called"] is None
    stock = make("inventory_runs_out_at_close")
    assert stock["calls"][0]["products"][0]["variant_id"]


def test_hard_case_lint_rejects_callback_outcome_mismatch():
    ref = btc_data()
    invalid = brief()
    invalid["hard_case_tags"] = ["callback_holiday"]
    invalid["calls"][0]["facts_to_establish"]["callback_requested_at"] = "2026-10-26T09:00"
    invalid["calls"][0]["success_if"] = {"tool_called": None}
    path = ROOT / "data_gen" / "tests" / "_bad_callback.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    try:
        errors = lint_one(path, ref)
        assert any("callback_holiday" in error for error in errors)
    finally:
        path.unlink(missing_ok=True)


def test_assembled_scenario_preserves_customer_id():
    b = brief("SC-DEMO-01")
    packs = {call["call_index"]: build_fact_pack(b, call["call_index"]) for call in b["calls"]}
    raw = {call["call_index"]: {"dialogue": [{"role": "customer", "text": "Tôi muốn hỏi thêm."}]} for call in b["calls"]}
    scenario = assemble_scenario(b, raw, packs)
    assert scenario["customer_id"] == b["customer_id"]


def test_batch_does_not_reuse_dry_run_raw_for_production():
    raw = ROOT / "data_gen" / "tests" / "_raw_mode_compat.json"
    raw.write_text(json.dumps({"generation_meta": {"provider": "dry-run", "model": "dry-run", "prompt_version": "customer_turns_v2", "seed": 7, "dry_run": True}}), encoding="utf-8")
    try:
        assert raw_requires_regeneration(raw, dry_run=False, seed=7)
        assert not raw_requires_regeneration(raw, dry_run=True, seed=7)
    finally:
        raw.unlink(missing_ok=True)


def test_btc_contract_inputs_are_present():
    validate_btc_contracts()


def test_generated_m1_artifacts_have_no_todo_briefs():
    briefs = sorted((ROOT / "data_gen" / "briefs").glob("SC-M1-*.json"))
    if not briefs:
        return
    assert len(briefs) >= 20
    for path in briefs:
        text = path.read_text(encoding="utf-8")
        assert '"TODO"' not in text


def test_generated_scenarios_match_public_sample_contract():
    b = brief("SC-DEMO-01")
    packs = {call["call_index"]: build_fact_pack(b, call["call_index"]) for call in b["calls"]}
    raw = {call["call_index"]: {"customer_turns": ["một", "hai", "ba", "bốn"]} for call in b["calls"]}
    scenario = assemble_scenario(b, raw, packs)
    scenarios = ROOT / "data_gen" / "tests" / "_contract_scenarios"
    scenarios.mkdir(exist_ok=True)
    path = scenarios / "SC-DEMO-01.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    try:
        validate_scenario_contract(scenarios, ROOT / "data_gen" / "briefs")
    finally:
        path.unlink(missing_ok=True)
        scenarios.rmdir()
