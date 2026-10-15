from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from .config import BRIEFS_DIR, BTC_DIR, DATA_GEN_DIR, RAW_DIR, REPORTS_DIR, SCENARIOS_DIR
from .lint_briefs import btc_data, lint_one


def validate_scenario_contract(directory: Path, briefs_dir: Path) -> None:
    """Validate the generated JSON against the BTC public-sample contract."""
    required_root_fields = {"scenario_id", "level", "persona", "hard_case", "customer_phone", "customer_name", "honorific", "notes", "calls"}
    allowed_call_fields = {
        "call_date", "days_later", "channel", "channel_identity", "customer_goal", "customer_turns",
        "customer_turns_asr", "input_mode", "seed_history", "facts_established", "must_carry_over",
        "must_not_ask", "success_if", "ground_truth_facts", "memory_expectation", "expected_outcome",
    }
    required_call_fields = {"call_date", "channel", "channel_identity", "customer_goal", "customer_turns", "success_if"}
    crm_customers = json.loads((BTC_DIR / "catalog/crm_seed.json").read_text(encoding="utf-8"))["customers"]
    for path in sorted(directory.glob("*.json")):
        if not (briefs_dir / path.name).exists():
            continue  # Orphaned legacy output is reported separately and never counts toward acceptance.
        scenario = json.loads(path.read_text(encoding="utf-8"))
        if not (scenario.get("scenario_id", "").startswith("SC-") and scenario["scenario_id"][3:].isdigit()):
            if not scenario.get("scenario_id", "").startswith("SC-DEMO-"):
                raise ValueError(f"{path.name}: scenario_id must use SC-NNN")
        if scenario.get("scenario_id") != path.stem:
            raise ValueError(f"{path.name}: filename must match scenario_id")
        if set(scenario) != required_root_fields:
            raise ValueError(f"{path.name}: root fields differ from public_sample contract; extras={sorted(set(scenario) - required_root_fields)} missing={sorted(required_root_fields - set(scenario))}")
        if not isinstance(scenario.get("calls"), dict) or not scenario["calls"]:
            raise ValueError(f"{path.name}: calls must be a non-empty object")
        for name, call in scenario["calls"].items():
            extra_fields = set(call) - allowed_call_fields
            if extra_fields:
                raise ValueError(f"{path.name}:{name}: unsupported call fields {sorted(extra_fields)}")
            missing = required_call_fields - set(call)
            if missing:
                raise ValueError(f"{path.name}:{name}: missing {sorted(missing)}")
            if not isinstance(call["customer_turns"], list) or not call["customer_turns"]:
                raise ValueError(f"{path.name}:{name}: customer_turns must be non-empty")
            asr_turns = call.get("customer_turns_asr")
            if not isinstance(asr_turns, list) or len(asr_turns) != len(call["customer_turns"]):
                raise ValueError(f"{path.name}:{name}: customer_turns_asr must be present and match clean turn count")
            if any(not isinstance(turn, str) or not turn.strip() for turn in asr_turns):
                raise ValueError(f"{path.name}:{name}: customer_turns_asr contains an empty/non-string turn")
            if not call["channel_identity"]:
                raise ValueError(f"{path.name}:{name}: channel_identity is empty")
        brief = json.loads((briefs_dir / path.name).read_text(encoding="utf-8"))
        if scenario.get("scenario_id") != brief.get("brief_id"):
            raise ValueError(f"{path.name}: scenario_id does not match brief_id")
        expected_hard_case = "_".join(brief.get("hard_case_tags", [])) or None
        if scenario.get("hard_case") != expected_hard_case or len(scenario["calls"]) != len(brief.get("calls", [])):
            raise ValueError(f"{path.name}: scenario hard-case/call count differs from its brief")
        for index, spec in enumerate(brief["calls"], start=1):
            generated = scenario["calls"].get(f"call_{index}", {})
            channel = spec.get("channel", brief.get("channel", "hotline"))
            identity_key = {"hotline": "phone", "chat_fanpage": "fb_id", "zalo_oa": "zalo_id"}[channel]
            caller_id = spec.get("customer_id", brief.get("customer_id"))
            crm_customer = next((item for item in crm_customers if item["customer_id"] == caller_id), {})
            expected_identity = spec.get("channel_identity") or crm_customer.get(identity_key)
            if generated.get("channel") != channel or generated.get("channel_identity") != expected_identity:
                raise ValueError(f"{path.name}:call_{index}: channel identity differs from brief")
            if spec.get("success_if") and generated.get("success_if") != spec.get("success_if"):
                raise ValueError(f"{path.name}:call_{index}: success_if differs from brief")


def validate_btc_contracts() -> None:
    """Fail early when the reference evaluator/simulator/public samples are unavailable."""
    evaluator = BTC_DIR / "eval" / "reference_eval.py"
    simulator_spec = BTC_DIR / "simulator" / "customer_simulator_spec.md"
    personas_path = BTC_DIR / "simulator" / "personas.json"
    public_dir = BTC_DIR / "test_set" / "public_sample"
    for path in (evaluator, simulator_spec, personas_path):
        if not path.exists():
            raise FileNotFoundError(f"Missing BTC contract input: {path}")
    samples = sorted(public_dir.glob("*.json"))
    if len(samples) < 7:
        raise ValueError(f"Expected at least 7 public samples, found {len(samples)}")
    personas = {
        item["persona_id"]
        for item in json.loads(personas_path.read_text(encoding="utf-8"))["personas"]
    }
    for path in samples:
        sample = json.loads(path.read_text(encoding="utf-8"))
        if sample.get("level") not in {"M1", "M2"} or sample.get("persona") not in personas:
            raise ValueError(f"{path.name}: invalid public-sample level/persona")
        if not isinstance(sample.get("calls"), dict) or not sample["calls"]:
            raise ValueError(f"{path.name}: calls must be an object")


def run_command(args: list[str]) -> None:
    completed = subprocess.run([sys.executable, *args], check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def preflight(briefs_dir: Path) -> None:
    reference = btc_data()
    failures = []
    for path in sorted(briefs_dir.glob("*.json")):
        errors = lint_one(path, reference)
        if errors:
            failures.append(f"{path.name}: " + "; ".join(errors))
    if failures:
        raise SystemExit("Brief preflight failed:\n- " + "\n- ".join(failures))


def artifact_coverage(briefs_dir: Path, scenarios_dir: Path) -> dict:
    """Summarize only generated scenario artifacts; planning slots are not counted."""
    dataset = json.loads((DATA_GEN_DIR / "dataset_config.json").read_text(encoding="utf-8"))
    targets = dataset["milestones"]["M1"]
    briefs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in briefs_dir.glob("SC-*.json")}
    scenarios = [
        value for p in scenarios_dir.glob("SC-*.json")
        if p.stem in briefs and re.fullmatch(r"SC-\d{3}", p.stem)
        for value in [json.loads(p.read_text(encoding="utf-8"))]
    ]
    transcript_count = sum(len(s.get("calls", {})) for s in scenarios)
    calls = [call for scenario in scenarios for call in scenario.get("calls", {}).values()]
    asr_count = sum(isinstance(call.get("customer_turns_asr"), list) for call in calls)
    paired_count = sum(
        isinstance(call.get("customer_turns"), list)
        and isinstance(call.get("customer_turns_asr"), list)
        and len(call["customer_turns"]) == len(call["customer_turns_asr"])
        for call in calls
    )
    calls_by_customer: dict[str, int] = {}
    channels_by_customer: dict[str, set[str]] = {}
    industry_region: set[tuple[str, str]] = set()
    catalog = json.loads((BTC_DIR / "catalog/products.json").read_text(encoding="utf-8")).get("products", [])
    category_by_sku = {}
    for product in catalog:
        industry = product.get("category", "").split("/", 1)[0]
        category_by_sku[product.get("sku")] = industry
        category_by_sku.update({variant.get("variant_sku"): industry for variant in product.get("variants", [])})
    crm_records = {
        record["customer_id"]: record
        for record in json.loads((BTC_DIR / "catalog/crm_seed.json").read_text(encoding="utf-8"))["customers"]
    }
    for scenario in scenarios:
        brief = briefs.get(scenario.get("scenario_id"), {})
        metadata_dir = scenarios_dir.with_name(f"{scenarios_dir.name}_metadata")
        try:
            sidecar = json.loads((metadata_dir / f"{scenario['scenario_id']}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sidecar = {}
        for call_name, call in scenario.get("calls", {}).items():
            customer_id = sidecar.get("call_customer_ids", {}).get(call_name, brief.get("customer_id"))
            if customer_id:
                calls_by_customer[customer_id] = calls_by_customer.get(customer_id, 0) + 1
                channels_by_customer.setdefault(customer_id, set()).add(call.get("channel", ""))
                region = crm_records.get(customer_id, {}).get("region")
            else:
                region = None
            for brief_call in brief.get("calls", []):
                if f"call_{brief_call.get('call_index')}" != call_name:
                    continue
                for item in brief_call.get("products", []):
                    industry = category_by_sku.get(item.get("variant_id") or item.get("sku"))
                    if industry and region:
                        industry_region.add((industry, region))
                break
    catalog_skus = {p.get("sku") for p in catalog if p.get("sku")}
    catalog_skus.update(v.get("variant_sku") for p in catalog for v in p.get("variants", []) if v.get("variant_sku"))
    metrics = {
        "scenario_count": len(scenarios),
        "transcript_count": transcript_count,
        "clean_transcript_count": transcript_count,
        "asr_transcript_count": asr_count,
        "paired_clean_asr_transcripts": paired_count,
        "multi_session_customers": sum(count >= 2 for count in calls_by_customer.values()),
        "multichannel_customers": sum(len(channels) > 1 for channels in channels_by_customer.values()),
        "industries": sorted({industry for industry, _ in industry_region}),
        "regions": sorted({region for _, region in industry_region}),
        "catalog_sku_count": len(catalog_skus),
        "audio_transcripts": 0,
        "audio_hours": 0.0,
    }
    metrics["text_targets_met"] = (
        metrics["transcript_count"] >= targets["transcripts_min"]
        and metrics["multi_session_customers"] >= targets["multi_session_customers_min"]
        and metrics["multichannel_customers"] >= targets["multichannel_customers_min"]
        and set(metrics["industries"]) == set(targets["industries"])
        and set(targets["regions"]).issubset(metrics["regions"])
        and metrics["catalog_sku_count"] >= targets["catalog_sku_min"]
    )
    metrics["m1_complete"] = False  # Audio is explicitly deferred in this generation phase.
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reproducible M1 text dataset pipeline.")
    parser.add_argument("--matrix", type=Path, default=REPORTS_DIR / "coverage_matrix.csv")
    parser.add_argument("--briefs", type=Path, default=BRIEFS_DIR)
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS_DIR)
    parser.add_argument("--raw", type=Path, default=RAW_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic offline customer-turn generation")
    parser.add_argument("--regenerate-matrix", action="store_true")
    parser.add_argument("--regenerate-briefs", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    validate_btc_contracts()
    if args.regenerate_matrix or not args.matrix.exists():
        run_command(["-m", "data_gen.coverage_matrix.make_coverage_matrix", "generate", "--force", "--out", str(args.matrix)])
    run_command([
        "-m", "data_gen.coverage_matrix.make_coverage_matrix", "stubs",
        "--matrix", str(args.matrix), "--out", str(args.briefs),
        *([] if not args.regenerate_briefs else ["--force"]),
    ])
    preflight(args.briefs)
    batch_args = [
        "-m", "data_gen.run_batch", "--briefs", str(args.briefs),
        "--out", str(args.scenarios), "--level", "M1",
    ]
    if args.dry_run:
        batch_args.append("--dry-run")
    if args.limit:
        batch_args.extend(["--limit", str(args.limit)])
    run_command(batch_args)
    run_command([
        "-m", "data_gen.auto_check", "--scenarios", str(args.scenarios),
        "--briefs", str(args.briefs), "--fact-packs", str(DATA_GEN_DIR / "fact_packs"),
    ])
    validate_scenario_contract(args.scenarios, args.briefs)
    coverage = artifact_coverage(args.briefs, args.scenarios)
    coverage_path = REPORTS_DIR / "artifact_coverage.json"
    coverage_path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tracking = REPORTS_DIR / "coverage_tracking.csv"
    run_command([
        "-m", "data_gen.coverage_matrix.make_coverage_matrix", "track",
        "--matrix", str(args.matrix), "--briefs", str(args.briefs),
        "--scenarios", str(args.scenarios), "--raw", str(args.raw), "--out", str(tracking),
    ])
    run_command([
        "-m", "data_gen.coverage_matrix.make_coverage_matrix", "report",
        "--matrix", str(tracking), "--defer-audio",
    ])
    print(json.dumps({
        "status": "partial_m1_audio_deferred",
        "phase": "M1_text_only",
        "audio": "deferred",
        "m1_complete": False,
        "artifact_coverage": str(coverage_path),
        "text_targets_met": coverage["text_targets_met"],
        "m2": "disabled",
        "matrix": str(args.matrix),
        "briefs": str(args.briefs),
        "scenarios": str(args.scenarios),
        "metadata": str(Path(args.scenarios).with_name(f"{Path(args.scenarios).name}_metadata")),
        "tracking": str(tracking),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
