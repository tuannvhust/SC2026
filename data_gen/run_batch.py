from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .assemble_scenario import run as assemble
from .config import FACT_PACKS_DIR, MODEL, PROMPT_VERSION, PROVIDER, REPORTS_DIR, RAW_DIR, SCENARIOS_DIR, load_dataset_config
from .gen_dialogue import generation_prompt, run as generate
from .facts import build_fact_pack
from .lint_briefs import btc_data, lint_one


def raw_requires_regeneration(raw_path: Path, *, dry_run: bool, seed: int, brief_digest: str | None = None, prompt_digest: str | None = None) -> bool:
    """Do not reuse dialogue generated in a different mode/configuration."""
    if not raw_path.exists():
        return True
    try:
        metadata = json.loads(raw_path.read_text(encoding="utf-8")).get("generation_meta", {})
    except (OSError, json.JSONDecodeError):
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


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--briefs",default=str(Path(__file__).parent / "briefs")); ap.add_argument("--out",default=str(SCENARIOS_DIR)); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--limit",type=int); ap.add_argument("--level",choices=("M1","M2"),default="M1"); ap.add_argument("--ready-only",action="store_true",help="Skip incomplete/invalid briefs and process only lint-clean briefs"); ap.add_argument("--force",action="store_true"); ap.add_argument("--seed",type=int,default=7); args=ap.parse_args()
    out_dir=Path(args.out); out_dir.mkdir(parents=True,exist_ok=True); manifest=REPORTS_DIR / "manifest.jsonl"; entries=[]
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
    mode = "dry-run" if args.dry_run else f"gemini:{MODEL}"
    print(f"[batch] start total={total} mode={mode} seed={args.seed} force={args.force}", flush=True)
    for position, path in enumerate(paths, start=1):
        brief=json.loads(path.read_text(encoding="utf-8")); sid=brief["brief_id"]; output=out_dir / f"{sid}.json"; status="ok"; error=None
        brief_digest=hashlib.sha256(json.dumps(brief,ensure_ascii=False,sort_keys=True).encode("utf-8")).hexdigest()
        scenario_num_calls = len(brief["calls"])
        prompt_digests = [generation_prompt(brief["persona_id"], call, scenario_num_calls)[1] for call in brief["calls"]]
        print(f"[{position}/{total}] START {sid} calls={len(brief['calls'])}", flush=True)
        try:
            compatible_raw = all(
                not raw_requires_regeneration(
                    RAW_DIR / f"{sid}_c{call['call_index']}.json",
                    dry_run=args.dry_run, seed=args.seed, brief_digest=brief_digest,
                    prompt_digest=generation_prompt(brief["persona_id"], call, scenario_num_calls)[1],
                )
                for call in brief["calls"]
            )
            if output.exists() and not args.force and compatible_raw:
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
                        brief_digest=brief_digest, prompt_digest=prompt_digests[idx - 1],
                    ):
                        print(f"[{position}/{total}] CALL  {sid} c{idx}: generating raw ({mode})", flush=True)
                        raw_generated=generate(brief,idx,args.seed,args.dry_run)
                        raw_data=json.loads(raw_generated.read_text(encoding="utf-8"))
                        raw_data["generation_meta"]["brief_digest"]=brief_digest
                        raw_generated.write_text(json.dumps(raw_data,ensure_ascii=False,indent=2),encoding="utf-8")
                    else:
                        print(f"[{position}/{total}] CALL  {sid} c{idx}: reusing compatible raw", flush=True)
                assembled=assemble(path,args.dry_run,out_dir=out_dir)
                if assembled.resolve() != output.resolve(): output=assembled
                print(f"[{position}/{total}] OK    {sid} output={output}", flush=True)
        except Exception as exc: status="failed"; error=str(exc)
        if status == "failed": print(f"[{position}/{total}] FAIL  {sid}: {error}", flush=True)
        entries.append({"brief_id":sid,"provider":"dry-run" if args.dry_run else PROVIDER,"prompt_version":PROMPT_VERSION,"prompt_digests":prompt_digests,"brief_digest":brief_digest,"model":"dry-run" if args.dry_run else MODEL,"seed":args.seed,"timestamp":datetime.now(timezone.utc).isoformat(),"status":status,"error":error})
    with manifest.open("a",encoding="utf-8") as f:
        for entry in entries: f.write(json.dumps(entry,ensure_ascii=False)+"\n")
    print(json.dumps({"status_counts":{s:sum(x["status"]==s for x in entries) for s in {x["status"] for x in entries}},"manifest":str(manifest)},ensure_ascii=False))


if __name__ == "__main__": main()
