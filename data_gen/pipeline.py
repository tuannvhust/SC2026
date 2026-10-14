from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .config import BRIEFS_DIR, BTC_DIR, DATA_GEN_DIR, RAW_DIR, REPORTS_DIR, SCENARIOS_DIR
from .lint_briefs import btc_data, lint_one


def validate_scenario_contract(directory: Path, briefs_dir: Path) -> None:
    """Validate the generated JSON against the BTC public-sample contract."""
    required_call_fields = {"call_date", "channel", "channel_identity", "customer_goal", "customer_turns", "success_if"}
    crm_customers = json.loads((BTC_DIR / "catalog/crm_seed.json").read_text(encoding="utf-8"))["customers"]
    for path in sorted(directory.glob("*.json")):
        scenario = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(scenario.get("calls"), dict) or not scenario["calls"]:
            raise ValueError(f"{path.name}: calls must be a non-empty object")
        for name, call in scenario["calls"].items():
            missing = required_call_fields - set(call)
            if missing:
                raise ValueError(f"{path.name}:{name}: missing {sorted(missing)}")
            if not isinstance(call["customer_turns"], list) or not call["customer_turns"]:
                raise ValueError(f"{path.name}:{name}: customer_turns must be non-empty")
            if not call["channel_identity"]:
                raise ValueError(f"{path.name}:{name}: channel_identity is empty")
        brief_path = briefs_dir / path.name
        if brief_path.exists():
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            if scenario.get("scenario_id") != brief.get("brief_id"):
                raise ValueError(f"{path.name}: scenario_id does not match brief_id")
            expected_hard_case = "_".join(brief.get("hard_case_tags", [])) or None
            if scenario.get("hard_case") != expected_hard_case or len(scenario["calls"]) != len(brief.get("calls", [])):
                raise ValueError(f"{path.name}: scenario hard-case/call count differs from its brief")
            for index, spec in enumerate(brief["calls"], start=1):
                generated = scenario["calls"].get(f"call_{index}", {})
                channel = spec.get("channel", brief.get("channel", "hotline"))
                identity_key = {"hotline": "phone", "chat_fanpage": "fb_id", "zalo_oa": "zalo_id"}[channel]
                crm_customer = next((item for item in crm_customers if item["customer_id"] == brief.get("customer_id")), {})
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
        "--out", str(args.scenarios), "--level", "M1", "--force",
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
        "status": "ok",
        "phase": "M1_text_only",
        "audio": "deferred",
        "m2": "disabled",
        "matrix": str(args.matrix),
        "briefs": str(args.briefs),
        "scenarios": str(args.scenarios),
        "tracking": str(tracking),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
