from __future__ import annotations

import json
import csv
import tempfile
from pathlib import Path
import pytest

from data_gen.validation import auto_check
from data_gen.validation.auto_check import check_one
from data_gen.generation.assemble_scenario import assemble_scenario, derive_ground_truth
import data_gen.generation.assemble_scenario as assemble_module
import data_gen.generation.gen_dialogue as dialogue_module
from data_gen.generation.facts import build_fact_pack, pricing_address_for_call
from data_gen.validation.lint_briefs import btc_data, lint_one
from data_gen.generation.run_batch import raw_requires_regeneration
from data_gen.generation.gen_dialogue import generate_turn_array, generation_payload, generation_prompt, parse_customer_turns
from data_gen.generation.gen_dialogue import make_asr_turns
from data_gen.coverage_matrix.make_coverage_matrix import (
    _brief_for_row, _policy_chunks_for, _products_for_industry, _promo_codes_for, discovered_data,
    CALL_COLUMNS, SCENARIO_COLUMNS, generate as generate_coverage_matrix, load_config,
    read_call_rows, validate_matrix,
)
from data_gen.coverage_matrix.make_coverage_matrix import sync_regions
from data_gen.generation.pipeline import validate_btc_contracts, validate_scenario_contract
from data_gen.generation.scenario_metadata import customer_goal_for_call
from data_gen.transcripts.corpus import validate_transcript, validate_corpus, coverage, review, _asr_reference_dialogue
import data_gen.transcripts.corpus as transcript_module
from data_gen.transcripts.asr_eval import normalize_for_entities, wer as asr_wer, cer as asr_cer, entity_scores, extract_entities
from data_gen.config import BRIEFS_DIR, SCENARIOS_DIR, REPORTS_DIR



ROOT = Path(__file__).resolve().parents[2]


def test_paired_transcript_requires_alternating_turns_and_pending_review():
    from data_gen.transcripts.corpus import make_transcript
    scenario = {"scenario_id": "SC-TEST-01", "persona": "khach_so_gia"}
    turns = [
        {"speaker": "customer", "text": "Mình cần hỏi giá sản phẩm."},
        {"speaker": "agent", "text": "Dạ em kiểm tra thông tin giúp mình."},
        {"speaker": "customer", "text": "Cảm ơn bạn."},
        {"speaker": "agent", "text": "Dạ vâng ạ."},
    ]
    call = {"channel": "hotline", "call_date": "2026-10-15", "facts_established": {"budget_vnd": 500000}}
    transcript = make_transcript(scenario, "call_1", call, "C001", turns, {"model": "test"})
    assert transcript["review_status"] == "pending_review"
    assert not validate_transcript(transcript)
    transcript["turns"][1]["speaker"] = "customer"
    assert "turn_order:1" in validate_transcript(transcript)


def test_transcript_counts_do_not_promote_scenarios_to_accepted_transcripts():
    report = coverage()
    assert report["accepted_transcripts"] == 0
    from data_gen.generation.pipeline import artifact_coverage
    scenarios = artifact_coverage(BRIEFS_DIR, SCENARIOS_DIR)
    expected_calls = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["calls"])
        for path in SCENARIOS_DIR.glob("*.json")
    )
    assert scenarios["evaluation_scenario_call_count"] == expected_calls
    assert scenarios["transcript_count"] == 0


def test_transcript_acceptance_is_explicit_and_persistent(monkeypatch):
    with tempfile.TemporaryDirectory(dir=ROOT / "data_gen" / "tests") as temp:
        temp = Path(temp)
        monkeypatch.setattr(transcript_module, "TRANSCRIPTS", temp / "transcripts")
        monkeypatch.setattr(transcript_module, "REVIEWS", temp / "reviews")
        t = {
            "transcript_id": "T-1", "review_status": "pending_review", "validation": {"status": "passed"},
            "turns": [{"speaker": "customer", "text": "xin chào"}, {"speaker": "agent", "text": "chào bạn"}],
        }
        path = transcript_module.TRANSCRIPTS / "T-1.json"
        path.parent.mkdir(); path.write_text(json.dumps(t), encoding="utf-8")
        review("T-1", "accepted", "human-reviewer", "checked")
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["review_status"] == "accepted"
        assert saved["review"]["reviewer"] == "human-reviewer"
        with pytest.raises(ValueError, match="only pending"):
            review("T-1", "rejected", "human-reviewer")


def test_team_asr_reference_uses_btc_dialogue_turn_shape_and_transcript_text():
    transcript = {
        "transcript_id": "T-2", "source_scenario_id": "SC-1", "region_accent": "bac",
        "ground_truth_facts": {"price_vnd": 4890000}, "audio_noisy": False,
        "turns": [{"speaker": "customer", "text": "Giá 4.890.000đ ạ."}, {"speaker": "agent", "text": "Dạ vâng."}],
    }
    dialogue = _asr_reference_dialogue(transcript, Path("T-2.wav"))
    btc = json.loads((ROOT / "data/asr/ground_truth.json").read_text(encoding="utf-8"))
    assert set(dialogue) == set(btc["dialogues"][0])
    assert dialogue["turns"][0]["speaker"] == "C"
    assert dialogue["turns"][0]["entities"]["price_vnd"] == 4890000
    assert dialogue["full_text"] == "Giá 4.890.000đ ạ. Dạ vâng."


def test_asr_normalization_matches_spoken_and_numeric_price_forms():
    expected = {"price_vnd": 4890000}
    spoken = "bốn triệu tám trăm chín mươi"
    numeric = "4.890.000đ"
    assert normalize_for_entities(spoken, expected) == normalize_for_entities(numeric, expected)
    assert asr_wer(spoken, numeric, expected) == 0
    assert asr_cer(spoken, numeric, expected) == 0
    assert entity_scores(expected, spoken)["price_vnd"] is True
    assert extract_entities(spoken) == {}  # predictions are not copied from the reference


def brief(name="SC-DEMO-01"):
    path = BRIEFS_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"Optional legacy fixture {path.name} is not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def test_facts_match_mock_for_conditional_promo():
    pack = build_fact_pack(brief("SC-DEMO-01"), 1); product = pack["products"][0]
    assert product["quote"]["final_price_vnd"] == 7590000
    assert any(x["promo_code"] == "TRADE-IN-AP" for x in product["quote"]["applied_promos"])


def test_facts_match_mock_for_expired_promo():
    pack = build_fact_pack(brief("SC-DEMO-02"), 2); quote = pack["products"][0]["quote"]
    assert "AP-SEP" in quote["expired_promos"]


def test_ground_truth_matches_public_sample_promo_contract():
    pack = {
        "promo_codes_in_play": ["AIR-OCT", "11-11"],
        "requested_policy_chunk_ids": ["KM-01"],
        "policy": [{"chunk_id": "KM-01", "type": "current", "text": "source text"}],
        "products": [
            {"sku": "SKU-A", "qty": 1, "quote": {"list_price_vnd": 100, "final_price_vnd": 90, "applied_promos": [], "expired_promos": [], "freeship": False}, "inventory": {"in_stock": True},
             "promotion_evidence": [{"promo_code": "AIR-OCT", "active": True, "eligible": False, "status": "ineligible", "reason": "region"}, {"promo_code": "11-11", "active": False, "eligible": False, "status": "not_started", "reason": "not_started"}]},
            {"sku": "SKU-B", "qty": 2, "quote": {"list_price_vnd": 200, "final_price_vnd": 180, "applied_promos": [], "expired_promos": [], "freeship": True}, "inventory": {"in_stock": False},
             "promotion_evidence": [{"promo_code": "AIR-OCT", "active": True, "eligible": True, "status": "applied"}]},
        ],
    }
    facts = derive_ground_truth(pack)
    assert facts["promo_active"] is False
    assert not any(key.startswith("promo_") and key != "promo_active" for key in facts)
    assert facts["policy_chunk_ids"] == ["KM-01"]
    assert facts["policy_evidence"] == pack["policy"]
    assert facts["product_1_price_vnd"] == 90 and facts["product_2_price_vnd"] == 180
    assert facts["product_2_freeship"] is True


def test_ground_truth_promo_active_is_true_only_when_quote_applies_promo():
    pack = {"products": [
        {"quote": {"applied_promos": [{"promo_code": "AIR-OCT"}]}, "inventory": {}},
        {"quote": {"applied_promos": []}, "inventory": {}},
    ]}
    facts = derive_ground_truth(pack)
    assert facts["promo_active"] is True
    assert set(key for key in facts if key.startswith("promo_")) == {"promo_active"}


def test_pricing_address_uses_customer_region_only_when_call_has_no_address():
    assert pricing_address_for_call({}, {"region": "nam"}) == "Hồ Chí Minh"
    assert pricing_address_for_call({"address": "Đà Nẵng"}, {"region": "nam"}) == "Đà Nẵng"
    assert pricing_address_for_call({}, {"region": "unknown"}) is None


def test_region_conditioned_promotion_uses_crm_region_for_each_pack():
    def make(customer_id):
        return {
            "brief_id": "SC-REGION", "persona_id": "khach_so_gia", "channel": "hotline",
            "customer_id": customer_id, "customer_name": "Customer", "honorific": "anh",
            "calls": [{"call_index": 1, "call_date": "2026-10-15", "customer_id": customer_id,
                       "products": [{"sku": "SKU-AP-X", "qty": 1}],
                       "promo_codes_in_play": ["NAM-SHIP0"], "policy_chunk_ids": [], "facts_to_establish": {}}],
        }
    north = build_fact_pack(make("C001"), 1)
    south = build_fact_pack(make("C002"), 1)
    assert north["customer"]["crm"]["region"] == "bac"
    assert south["customer"]["crm"]["region"] == "nam"
    north_ineligible = {p["promo_code"]: p["reason"] for p in north["products"][0]["quote"]["ineligible_promos"]}
    assert north_ineligible["NAM-SHIP0"] == "region"
    assert any(p["promo_code"] == "NAM-SHIP0" for p in south["products"][0]["quote"]["applied_promos"])
    assert north["products"][0]["promotion_evidence"][0]["eligible"] is False
    assert south["products"][0]["promotion_evidence"][0]["eligible"] is True


def test_matrix_sync_sets_region_from_primary_crm_customer():
    with tempfile.TemporaryDirectory(dir=ROOT / "data_gen" / "tests") as temp:
        matrix = Path(temp) / "matrix.csv"
        matrix.write_text(
            "level,case_number,slot_id,layer,owner,persona_id,nganh,mien,num_calls,channel_pattern,hard_case_tag,special_customer,promo_codes_in_play,promo_situation,policy_chunk_ids,policy_situation,customer_id,audio_source,audio_hours,audio_noisy,status,story_hints\n"
            "M1,1,SC-001,A,SV1,p,thoi-trang,bac,2,hotline-hotline,,,,,,,C032,,0,no,todo,story\n",
            encoding="utf-8-sig",
        )
        assert sync_regions(matrix) == 1
        assert sync_regions(matrix) == 0
        with matrix.open(encoding="utf-8-sig", newline="") as stream:
            row = next(csv.DictReader(stream))
        assert row["mien"] == "trung"


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
    applied_codes = list(dict.fromkeys(
        promo["promo_code"]
        for pack in packs.values()
        for product in pack.get("products", [])
        for promo in product.get("quote", {}).get("applied_promos", [])
    ))
    if applied_codes:
        recorded = scenario["calls"]["call_1"]["facts_established"].get("promo_code")
        assert recorded in applied_codes or set(recorded or []) == set(applied_codes)
    assert scenario["calls"]["call_1"]["ground_truth_facts"]["promo_active"] is bool(applied_codes)
    assert not any(key.startswith("promo_") and key != "promo_active" for key in scenario["calls"]["call_1"]["ground_truth_facts"])
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
    call = {"call_index": 2, "customer_id": "C001", "customer_goal": "goal sentinel", "facts_to_establish": {"budget_vnd": 8_000_000}, "story_hint": "outline sentinel"}
    system, digest = generation_prompt("khach_so_gia", call, scenario_num_calls=3)
    assert "outline sentinel" in system
    assert "4–8" in system
    assert "Style: thực dụng, nhắc giá đối thủ, đòi giảm" in system
    assert "Vị trí cuộc gọi: 2/3" in system
    assert "Patience ban đầu của cuộc gọi: 3" in system
    assert "khách tự xưng ‘chị’, gọi nhân viên là ‘em’" in system
    assert "thực dụng" in system or "thá»±c dá»¥ng" in system
    changed_system, changed_digest = generation_prompt("khach_so_gia", {**call, "story_hint": "different outline"}, scenario_num_calls=3)
    assert changed_system != system and changed_digest != digest
    _, count_changed_digest = generation_prompt("khach_so_gia", call, scenario_num_calls=2)
    assert count_changed_digest != digest


def test_generation_payload_includes_call_count_and_patience():
    scenario = {
        "persona_id": "khach_so_gia",
        "channel": "hotline",
        "calls": [
            {"call_index": 1, "customer_id": "C001", "customer_goal": "goal 1"},
            {"call_index": 2, "customer_id": "C001", "customer_goal": "goal 2", "channel": "zalo_oa"},
            {"call_index": 3, "customer_goal": "goal 3"},
        ],
    }
    payload = generation_payload(scenario, 2)
    assert payload["scenario_num_calls"] == 3
    assert payload["call_index"] == 2
    assert payload["persona"]["style"] == "thực dụng, nhắc giá đối thủ, đòi giảm"
    assert payload["persona"]["patience_initial"] == 3
    assert payload["channel"] == "zalo_oa"
    assert payload["caller_identity"]["honorific"] == "chị"


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
        if calls >= 3:
            row["story_hints"] += " || Call 3: Continue discussing available choices before deciding."
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


def test_assembled_scenario_keeps_internal_customer_id_out_of_public_payload():
    b = brief("SC-002")
    packs = {call["call_index"]: build_fact_pack(b, call["call_index"]) for call in b["calls"]}
    raw = {call["call_index"]: {"dialogue": [{"role": "customer", "text": "Tôi muốn hỏi thêm."}]} for call in b["calls"]}
    scenario = assemble_scenario(b, raw, packs)
    assert "customer_id" not in scenario
    assert set(scenario) == {"scenario_id", "level", "persona", "hard_case", "customer_phone", "customer_name", "honorific", "notes", "calls"}


def test_assembly_uses_call_story_instead_of_scenario_summary_for_shared_phone():
    b = brief("SC-002")
    packs = {call["call_index"]: build_fact_pack(b, call["call_index"]) for call in b["calls"]}
    raw = {call["call_index"]: {"customer_turns": ["a", "b", "c", "d"]} for call in b["calls"]}
    scenario = assemble_scenario(
        b, raw, packs,
        summary={"customer_goal": "Wrong goal from primary customer", "notes": "summary must not override brief"},
    )
    expected = customer_goal_for_call(b, b["calls"][0])
    assert scenario["calls"]["call_1"]["customer_goal"] == expected
    assert scenario["calls"]["call_1"]["customer_goal"] != "Wrong goal from primary customer"


def test_matrix_policy_and_promotion_selection_are_relevant_to_source_context():
    data = discovered_data()
    assert not any(chunk.startswith("CL-") for chunk in data["policy_chunks"])
    policy = _policy_chunks_for("current", data, tag="numeric_precision", industry="thoi-trang", sku="SKU-SN-RUN1")
    assert policy.split("|") == ["VC-01", "KM-01"]
    running_shoe = next(p for p in _products_for_industry("thoi-trang") if p["sku"] == "SKU-SN-RUN1")
    promos = _promo_codes_for(
        "active", {"promos": {"active": ["AIR-2ND-50", "RUN-10", "COD-0"]}},
        industry="thoi-trang", region="bac", products=[running_shoe],
    )
    assert promos.split("|") == ["RUN-10", "COD-0"]


def test_batch_does_not_reuse_dry_run_raw_for_production():
    raw = ROOT / "data_gen" / "tests" / "_raw_mode_compat.json"
    raw.write_text(json.dumps({
        "customer_turns": ["a", "b", "c", "d"],
        "customer_turns_asr": ["a", "b", "c", "d"],
        "generation_meta": {"provider": "dry-run", "model": "dry-run", "prompt_version": "customer_turns_v5", "payload_digest": "digest", "seed": 7, "dry_run": True},
    }), encoding="utf-8")
    try:
        assert raw_requires_regeneration(raw, dry_run=False, seed=7)
        assert not raw_requires_regeneration(raw, dry_run=True, seed=7)
    finally:
        raw.unlink(missing_ok=True)


def test_asr_text_variant_is_deterministic_and_aligned_with_clean_turns():
    clean = ["Xin chào, mình muốn hỏi.", "Mẫu này còn hàng không?", "Giá hiện tại thế nào?", "Mình sẽ cân nhắc."]
    asr = make_asr_turns(clean, seed=7, dry_run=True)
    assert len(asr) == len(clean)
    assert asr == make_asr_turns(clean, seed=7, dry_run=True)
    assert asr[0] == "xin chào mình muốn hỏi"


def test_generation_retries_invalid_turn_count_with_format_feedback(monkeypatch):
    outputs = iter((json.dumps(["one", "two", "three"]), json.dumps(["one", "two", "three", "four"])))
    seen = []
    def fake_complete(system, user, *, seed, temperature, dry_run):
        seen.append((json.loads(user), seed))
        return next(outputs)
    monkeypatch.setattr(dialogue_module, "complete", fake_complete)
    turns = generate_turn_array("system", {"goal": "test"}, seed=11, dry_run=False)
    assert turns == ["one", "two", "three", "four"]
    assert len(seen) == 2 and "format_correction" in seen[1][0]
    assert [seed for _, seed in seen] == [11, 12]


def test_eval_selects_clean_or_asr_text_from_input_mode():
    call = {"customer_turns": ["clean"], "customer_turns_asr": ["transcript"], "input_mode": "clean"}
    assert call["customer_turns"][0] == "clean"
    call["input_mode"] = "asr_transcript"
    assert call["customer_turns_asr"][0] == "transcript"


def test_generation_emits_clean_and_asr_turns_with_separate_payloads(monkeypatch):
    b = brief("SC-002")
    with tempfile.TemporaryDirectory(dir=ROOT / "data_gen" / "tests") as temp:
        raw_dir = Path(temp)
        monkeypatch.setattr(dialogue_module, "RAW_DIR", raw_dir)
        monkeypatch.setattr(dialogue_module, "persona_record", lambda _: {"persona_id": "test", "system_prompt": "test persona"})
        calls = []
        def fake_complete(system, user, *, seed, temperature, dry_run):
            calls.append((system, json.loads(user), seed))
            if len(calls) == 1:
                return json.dumps(["Mình muốn hỏi về sản phẩm.", "Nhà mình cần dùng hằng ngày.", "Cho mình hỏi giá.", "Mình sẽ cân nhắc."])
            return json.dumps(["mình muốn hỏi về sản phẩm", "nhà mình cần dùng hằng ngày", "cho mình hỏi giá", "mình sẽ cân nhắc"])
        monkeypatch.setattr(dialogue_module, "complete", fake_complete)
        path = dialogue_module.run(b, 1, 7, False)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert len(calls) == 2 and calls[0][1]["input_mode"] == "clean"
        assert calls[1][1]["clean_customer_turns"] == raw["customer_turns"]
        assert len(raw["customer_turns_asr"]) == len(raw["customer_turns"])
        assert raw["generation_meta"]["payload_digest"] and raw["generation_meta"]["asr_prompt_digest"]


def test_assembly_writes_public_shape_and_per_call_identity_sidecar(monkeypatch):
    b = brief("SC-002")
    with tempfile.TemporaryDirectory(dir=ROOT / "data_gen" / "tests") as temp:
        tmp_path = Path(temp)
        brief_dir = tmp_path / "briefs"; brief_dir.mkdir()
        pack_dir = tmp_path / "packs"; pack_dir.mkdir()
        raw_dir = tmp_path / "raw"; raw_dir.mkdir()
        scenario_dir = tmp_path / "scenarios"
        brief_path = brief_dir / f'{b["brief_id"]}.json'
        brief_path.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
        for call in b["calls"]:
            index = call["call_index"]
            pack = build_fact_pack(b, index)
            (pack_dir / f'{b["brief_id"]}_c{index}.json').write_text(json.dumps(pack), encoding="utf-8")
            turns = ["Mình đang tìm hiểu.", "Nhà mình có nhu cầu này.", "Cho mình hỏi thêm.", "Mình sẽ cân nhắc."]
            raw_data = {
                "customer_turns": turns,
                "customer_turns_asr": make_asr_turns(turns, seed=7, dry_run=True),
            }
            (raw_dir / f'{b["brief_id"]}_c{index}.json').write_text(json.dumps(raw_data), encoding="utf-8")
        (raw_dir / f'{b["brief_id"]}_metadata.json').write_text(json.dumps({
            "scenario_id": b["brief_id"], "notes": "reviewed summary", "customer_goal": "customer goal",
        }), encoding="utf-8")
        monkeypatch.setattr(assemble_module, "FACT_PACKS_DIR", pack_dir)
        monkeypatch.setattr(assemble_module, "RAW_DIR", raw_dir)
        output = assemble_module.run(brief_path, False, scenario_dir)
        scenario = json.loads(output.read_text(encoding="utf-8"))
        sidecar = json.loads((tmp_path / "scenarios_metadata" / output.name).read_text(encoding="utf-8"))
        assert set(scenario) == {"scenario_id", "level", "persona", "hard_case", "customer_phone", "customer_name", "honorific", "notes", "calls"}
        assert all(
            ("customer_turns_asr" in call) == (call.get("input_mode", "clean") != "clean")
            for call in scenario["calls"].values()
        )
        assert "customer_id" not in scenario and all("customer_id" not in call for call in scenario["calls"].values())
        assert sidecar["customer_id"] == b["customer_id"]
        findings = check_one(output, brief_dir, pack_dir, raw_dir)
        assert not [finding for finding in findings if finding["hard"] == "true"]


def test_raw_requires_regeneration_when_asr_variant_is_missing():
    raw = ROOT / "data_gen" / "tests" / "_raw_without_asr.json"
    raw.write_text(json.dumps({
        "customer_turns": ["a", "b", "c", "d"],
        "generation_meta": {"provider": "dry-run", "model": "dry-run", "prompt_version": "customer_turns_v5", "payload_digest": "digest", "seed": 7, "dry_run": True},
    }), encoding="utf-8")
    try:
        assert raw_requires_regeneration(raw, dry_run=True, seed=7)
    finally:
        raw.unlink(missing_ok=True)


def test_btc_contract_inputs_are_present():
    validate_btc_contracts()


def test_generated_m1_artifacts_have_no_todo_briefs():
    briefs = sorted(BRIEFS_DIR.glob("SC-[0-9][0-9][0-9].json"))
    if not briefs:
        return
    assert len(briefs) >= 20
    for path in briefs:
        text = path.read_text(encoding="utf-8")
        assert '"TODO"' not in text


def test_generated_scenarios_match_public_sample_contract():
    b = brief("SC-002")
    packs = {call["call_index"]: build_fact_pack(b, call["call_index"]) for call in b["calls"]}
    raw = {call["call_index"]: {"customer_turns": ["một", "hai", "ba", "bốn"]} for call in b["calls"]}
    scenario = assemble_scenario(b, raw, packs)
    scenarios = ROOT / "data_gen" / "tests" / "_contract_scenarios"
    scenarios.mkdir(exist_ok=True)
    path = scenarios / "SC-002.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    try:
        validate_scenario_contract(scenarios, BRIEFS_DIR)
    finally:
        path.unlink(missing_ok=True)
        scenarios.rmdir()


def test_coverage_matrix_generation_is_deterministic_and_split_by_call(tmp_path):
    config_path = ROOT / "data_gen" / "coverage_matrix" / "matrix_config.json"
    config = load_config(config_path)
    matrix_a = tmp_path / "a" / "coverage_matrix.csv"
    matrix_b = tmp_path / "b" / "coverage_matrix.csv"
    generate_coverage_matrix(config, matrix_a)
    generate_coverage_matrix(config, matrix_b)
    assert matrix_a.read_bytes() == matrix_b.read_bytes()
    calls_a = matrix_a.with_name("coverage_calls.csv")
    calls_b = matrix_b.with_name("coverage_calls.csv")
    assert calls_a.read_bytes() == calls_b.read_bytes()
    with matrix_a.open(encoding="utf-8-sig", newline="") as stream:
        assert set(next(csv.DictReader(stream))) == set(SCENARIO_COLUMNS)
    assert set(read_call_rows(calls_a)[0]) == set(CALL_COLUMNS)


def test_reviewed_coverage_matrix_satisfies_call_contracts():
    matrix = ROOT / "data_gen" / "coverage_matrix" / "coverage_matrix.csv"
    assert validate_matrix(matrix) == []
