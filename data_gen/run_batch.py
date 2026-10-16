from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .assemble_scenario import run as assemble
from .config import BTC_DIR, FACT_PACKS_DIR, MODEL, PROMPT_VERSION, PROVIDER, REPORTS_DIR, RAW_DIR, SCENARIOS_DIR, load_dataset_config
from .gen_dialogue import generation_prompt, persona_record, run as generate
from .facts import build_fact_pack
from .lint_briefs import btc_data, lint_one
from .provenance import brief_digest
from .scenario_metadata import (
    customer_goal_for_call,
    hard_case_label,
    generate_scenario_summary,
    scenario_summary_is_reusable,
    scenario_summary_path,
    scenario_summary_payload,
    scenario_notes,
)


def raw_requires_regeneration(raw_path: Path, *, dry_run: bool, seed: int, brief_digest: str | None = None, prompt_digest: str | None = None) -> bool:
    """Do not reuse dialogue generated in a different mode/configuration."""
    if not raw_path.exists():
        return True
    try:
        raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
        metadata = raw_data.get("generation_meta", {})
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(raw_data.get("customer_turns"), list) or not isinstance(raw_data.get("customer_turns_asr"), list):
        return True
    if len(raw_data["customer_turns"]) != len(raw_data["customer_turns_asr"]):
        return True
    if not metadata.get("payload_digest"):
        return True
    if bool(metadata.get("dry_run")) != dry_run or metadata.get("seed") != seed:
        return True
    if metadata.get("prompt_version") != PROMPT_VERSION:
        return True
    if brief_digest is not None and metadata.get("brief_digest") != brief_digest:
        return True
    if prompt_digest is not None and metadata.get("prompt_digest") != prompt_digest:
        return True
    if not dry_run and (metadata.get("provider") != PROVIDER or metadata.get("model") != MODEL):
        return True
    return False


def brief_order(path: Path) -> tuple[int, int, str]:
    """Sort legacy briefs as M1 and keep M2 after every M1 brief."""
    dataset_config = load_dataset_config()
    levels = dataset_config.get("ordering", {}).get("levels", ["M1", "M2"])
    try:
        brief = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (99, 999999, path.name)
    level = brief.get("level", "M1").upper()
    level_rank = {name: rank for rank, name in enumerate(levels)}.get(level, 99)
    number = brief.get("case_number")
    if not isinstance(number, int):
        match = re.search(r"(?:M[12][-_])?(\d+)$", brief.get("brief_id", ""))
        number = int(match.group(1)) if match else 999999
    return (level_rank, number, brief.get("brief_id", path.name))


def repository_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={Path(__file__).resolve().parents[1]}", "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def scenario_needs_assembly(path: Path, brief: dict | None = None, summary: dict | None = None) -> bool:
    """Detect output created before the public-sample field contract/ASR turns."""
    if not path.exists():
        return True
    try:
        scenario = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    root_fields = {"scenario_id", "level", "persona", "hard_case", "customer_phone", "customer_name", "honorific", "notes", "calls"}
    if set(scenario) != root_fields:
        return True
    allowed_call_fields = {
        "call_date", "days_later", "channel", "channel_identity", "customer_goal", "customer_turns",
        "customer_turns_asr", "input_mode", "seed_history", "facts_established", "must_carry_over",
        "must_not_ask", "success_if", "ground_truth_facts", "memory_expectation", "expected_outcome",
    }
    metadata_path = path.parent.with_name(f"{path.parent.name}_metadata") / path.name
    if not metadata_path.exists() or not isinstance(summary, dict):
        return True
    try:
        sidecar = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if brief is not None:
        story_hints = {
            f"call_{call['call_index']}": call.get("story_hint", "")
            for call in brief.get("calls", [])
        }
        first_call = next((call for call in brief.get("calls", []) if call.get("call_index") == 1), {})
        if (
            scenario.get("hard_case") != hard_case_label(brief.get("hard_case_tags", []))
            or scenario.get("notes") != scenario_notes(brief)
            or scenario.get("calls", {}).get("call_1", {}).get("customer_goal") != customer_goal_for_call(brief, first_call)
            or sidecar.get("story_hints") != story_hints
            or any("customer_goal" in call for name, call in scenario.get("calls", {}).items() if name != "call_1")
        ):
            return True
    return any(
        (
            call.get("input_mode", "clean") != "clean"
            and (
                not isinstance(call.get("customer_turns_asr"), list)
                or len(call["customer_turns_asr"]) != len(call.get("customer_turns", []))
            )
        )
        or "customer_id" in call
        or "customer_name" in call
        or "teencode_level" in call
        or set(call) - allowed_call_fields
        for call in scenario.get("calls", {}).values()
    )


def source_digest() -> str:
    digest = hashlib.sha256()
    relatives = [
        "catalog/products.json", "catalog/crm_seed.json", "catalog/promotions.json",
        "catalog/inventory_timeline.json", "simulator/personas.json", "eval/mock_tools.py",
    ]
    relatives.extend(str(path.relative_to(BTC_DIR)).replace("\\", "/") for path in sorted((BTC_DIR / "policy").glob("*.md")))
    for relative in relatives:
        path = BTC_DIR / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def code_digest() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).parent
    for relative in (
        "config.py", "gen_dialogue.py", "assemble_scenario.py", "facts.py", "run_batch.py",
        "pipeline.py", "lint_briefs.py", "auto_check.py", "scenario_metadata.py",
        "prompts/customer_turns_v5.txt", "prompts/scenario_metadata_v1.txt",
        "prompts/customer_input_modes_v1.txt", "provenance.py",
        "coverage_matrix/make_coverage_matrix.py",
    ):
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--briefs",default=str(Path(__file__).parent / "briefs"))
    ap.add_argument("--out",default=str(SCENARIOS_DIR))
    ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--limit",type=int)
    ap.add_argument("--level",choices=("M1","M2"),default="M1")
    ap.add_argument("--ready-only",action="store_true",help="Skip incomplete/invalid briefs and process only lint-clean briefs")
    ap.add_argument("--force",action="store_true")
    ap.add_argument("--assemble-only",action="store_true",help="Rebuild scenarios from existing raw turns and fact packs without calling the LLM")
    ap.add_argument("--seed",type=int,default=7)
    args=ap.parse_args()
    
    out_dir=Path(args.out)
    out_dir.mkdir(parents=True,exist_ok=True); manifest=REPORTS_DIR / "manifest.jsonl"; entries=[]
    paths=sorted(Path(args.briefs).glob("*.json"), key=brief_order)
    selected=[]
    for path in paths:
        try:
            candidate=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):
            if args.ready_only:
                print(f"[batch] NOT_READY {path.name}: invalid JSON",flush=True)
                continue
            raise
        if candidate.get("level","M1").upper() == args.level:
            selected.append(path)
    paths=selected
    reference=btc_data()
    invalid=[]; ready=[]
    for path in paths:
        errors=lint_one(path,reference)
        if errors:
            invalid.append(f"{path.name}: " + "; ".join(errors))
            if args.ready_only:
                print(f"[batch] NOT_READY {path.name}: " + "; ".join(errors),flush=True)
        else:
            ready.append(path)
    if args.ready_only:
        paths=ready
    if args.limit:
        paths=paths[:args.limit]
    if invalid and not args.ready_only:
        raise SystemExit("Batch preflight failed:\n- " + "\n- ".join(invalid))
    total = len(paths)
    mode = "assemble-only (no LLM)" if args.assemble_only else "dry-run" if args.dry_run else f"gemini:{MODEL}"
    print(f"[batch] start total={total} mode={mode} seed={args.seed} force={args.force}", flush=True)
    for position, path in enumerate(paths, start=1):
        brief=json.loads(path.read_text(encoding="utf-8")); sid=brief["brief_id"]; output=out_dir / f"{sid}.json"; status="ok"; error=None
        brief_digest_value=brief_digest(brief)
        scenario_num_calls = len(brief["calls"])
        prompt_digests = [generation_prompt(brief["persona_id"], call, scenario_num_calls)[1] for call in brief["calls"]]
        summary_path = scenario_summary_path(RAW_DIR, sid)
        summary_seed = args.seed + int(brief.get("case_number", 0))
        summary_prompt_digest = hashlib.sha256(
            ("scenario_metadata_v1\n" + (Path(__file__).parent / "prompts/scenario_metadata_v1.txt").read_text(encoding="utf-8").strip()).encode("utf-8")
        ).hexdigest()
        print(f"[{position}/{total}] START {sid} calls={len(brief['calls'])}", flush=True)
        try:
            def raw_artifacts_current() -> bool:
                return all(
                    not raw_requires_regeneration(
                        RAW_DIR / f"{sid}_c{call['call_index']}.json",
                        dry_run=args.dry_run, seed=args.seed, brief_digest=brief_digest_value,
                        prompt_digest=generation_prompt(brief["persona_id"], call, scenario_num_calls)[1],
                    )
                    for call in brief["calls"]
                )

            def load_raw_calls() -> dict[int, dict]:
                return {
                    call["call_index"]: json.loads((RAW_DIR / f"{sid}_c{call['call_index']}.json").read_text(encoding="utf-8"))
                    for call in brief["calls"]
                }

            persona = persona_record(brief["persona_id"])
            raw_current = raw_artifacts_current()
            raw_by_call = load_raw_calls() if raw_current else {}
            summary_payload = scenario_summary_payload(brief, raw_by_call, persona) if raw_current else None
            try:
                summary_artifact = json.loads(summary_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                summary_artifact = None
            summary_current = bool(summary_payload) and scenario_summary_is_reusable(
                summary_artifact, summary_payload, seed=summary_seed, dry_run=args.dry_run,
                model=MODEL, provider=PROVIDER,
            )
            if args.assemble_only:
                missing = [
                    artifact.name
                    for call in brief["calls"]
                    for artifact in (
                        RAW_DIR / f"{sid}_c{call['call_index']}.json",
                        FACT_PACKS_DIR / f"{sid}_c{call['call_index']}.json",
                    )
                    if not artifact.exists()
                ]
                if missing or not raw_current:
                    raise FileNotFoundError(
                        "assemble-only needs prompt-compatible customer turns and fact packs; "
                        + (", ".join(missing) if missing else "regenerate this scenario with a normal batch first")
                    )
                assembled=assemble(path,args.dry_run,out_dir=out_dir)
                if assembled.resolve() != output.resolve(): output=assembled
                status="assembled"
                print(f"[{position}/{total}] ASSEMBLED {sid} from saved artifacts", flush=True)
            elif output.exists() and not args.force and raw_current and summary_current and not scenario_needs_assembly(output, brief, summary_artifact):
                status="skipped"
                print(f"[{position}/{total}] SKIP  {sid} output_exists={output}", flush=True)
            else:
                for call in brief["calls"]:
                    idx=call["call_index"]
                    pack_path=FACT_PACKS_DIR / f"{sid}_c{idx}.json"
                    pack_path.write_text(json.dumps(build_fact_pack(brief,idx),ensure_ascii=False,indent=2),encoding="utf-8")
                    raw_path=RAW_DIR / f"{sid}_c{idx}.json"
                    if args.force or raw_requires_regeneration(
                        raw_path, dry_run=args.dry_run, seed=args.seed,
                        brief_digest=brief_digest_value, prompt_digest=prompt_digests[idx - 1],
                    ):
                        print(f"[{position}/{total}] CALL  {sid} c{idx}: generating raw ({mode})", flush=True)
                        raw_generated=generate(brief,idx,args.seed,args.dry_run)
                        raw_data=json.loads(raw_generated.read_text(encoding="utf-8"))
                        raw_data["generation_meta"]["brief_digest"]=brief_digest_value
                        raw_generated.write_text(json.dumps(raw_data,ensure_ascii=False,indent=2),encoding="utf-8")
                    else:
                        print(f"[{position}/{total}] CALL  {sid} c{idx}: reusing compatible raw", flush=True)
                raw_by_call = load_raw_calls()
                summary_payload = scenario_summary_payload(brief, raw_by_call, persona)
                if args.force or not scenario_summary_is_reusable(
                    summary_artifact, summary_payload, seed=summary_seed, dry_run=args.dry_run,
                    model=MODEL, provider=PROVIDER,
                ):
                    print(f"[{position}/{total}] SUMM {sid}: synthesizing scenario metadata", flush=True)
                    summary_artifact = generate_scenario_summary(
                        brief, raw_by_call, persona, seed=summary_seed, dry_run=args.dry_run,
                        model=MODEL, provider=PROVIDER,
                    )
                    summary_path.write_text(json.dumps(summary_artifact,ensure_ascii=False,indent=2),encoding="utf-8")
                else:
                    print(f"[{position}/{total}] SUMM {sid}: reusing saved scenario metadata", flush=True)
                assembled=assemble(path,args.dry_run,out_dir=out_dir)
                if assembled.resolve() != output.resolve(): output=assembled
                print(f"[{position}/{total}] OK    {sid} output={output}", flush=True)
        except Exception as exc: status="failed"; error=str(exc)
        if status == "failed": print(f"[{position}/{total}] FAIL  {sid}: {error}", flush=True)
        output_digest = None
        sidecar_digest = None
        if status in {"ok", "skipped", "assembled"} and output.exists():
            output_digest = hashlib.sha256(output.read_bytes()).hexdigest()
            sidecar = output.parent.with_name(f"{output.parent.name}_metadata") / output.name
            if sidecar.exists():
                sidecar_digest = hashlib.sha256(sidecar.read_bytes()).hexdigest()
        entries.append({"brief_id":sid,"provider":"dry-run" if args.dry_run else PROVIDER,"prompt_version":PROMPT_VERSION,"prompt_digests":prompt_digests,"scenario_metadata_prompt_digest":summary_prompt_digest,"scenario_metadata_seed":summary_seed,"brief_digest":brief_digest_value,"source_digest":source_digest(),"code_digest":code_digest(),"model":"dry-run" if args.dry_run else MODEL,"seed":args.seed,"code_revision":repository_revision(),"output_digest":output_digest,"sidecar_digest":sidecar_digest,"timestamp":datetime.now(timezone.utc).isoformat(),"status":status,"error":error})
    with manifest.open("a",encoding="utf-8") as f:
        for entry in entries: f.write(json.dumps(entry,ensure_ascii=False)+"\n")
    status_counts = {s: sum(x["status"] == s for x in entries) for s in {x["status"] for x in entries}}
    print(json.dumps({"status_counts": status_counts, "manifest": str(manifest)}, ensure_ascii=False))
    if status_counts.get("failed", 0):
        raise SystemExit(1)


if __name__ == "__main__": main()
