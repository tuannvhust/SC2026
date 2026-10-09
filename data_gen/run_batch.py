from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .assemble_scenario import run as assemble
from .config import FACT_PACKS_DIR, MODEL, PROMPT_VERSION, PROVIDER, REPORTS_DIR, RAW_DIR, SCENARIOS_DIR
from .gen_dialogue import run as generate
from .facts import build_fact_pack


def raw_requires_regeneration(raw_path: Path, *, dry_run: bool, seed: int) -> bool:
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
    if not dry_run and (metadata.get("provider") != PROVIDER or metadata.get("model") != MODEL):
        return True
    return False


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--briefs",default=str(Path(__file__).parent / "briefs")); ap.add_argument("--out",default=str(SCENARIOS_DIR)); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--limit",type=int); ap.add_argument("--force",action="store_true"); ap.add_argument("--seed",type=int,default=7); args=ap.parse_args()
    out_dir=Path(args.out); out_dir.mkdir(exist_ok=True); manifest=REPORTS_DIR / "manifest.jsonl"; entries=[]
    paths=sorted(Path(args.briefs).glob("*.json")); paths=paths[:args.limit] if args.limit else paths
    total = len(paths)
    mode = "dry-run" if args.dry_run else f"gemini:{MODEL}"
    print(f"[batch] start total={total} mode={mode} seed={args.seed} force={args.force}", flush=True)
    for position, path in enumerate(paths, start=1):
        brief=json.loads(path.read_text(encoding="utf-8")); sid=brief["brief_id"]; output=out_dir / f"{sid}.json"; status="ok"; error=None
        print(f"[{position}/{total}] START {sid} calls={len(brief['calls'])}", flush=True)
        try:
            if output.exists() and not args.force:
                status="skipped"
                print(f"[{position}/{total}] SKIP  {sid} output_exists={output}", flush=True)
            else:
                for call in brief["calls"]:
                    idx=call["call_index"]
                    pack_path=FACT_PACKS_DIR / f"{sid}_c{idx}.json"
                    if args.force or not pack_path.exists(): pack_path.write_text(json.dumps(build_fact_pack(brief,idx),ensure_ascii=False,indent=2),encoding="utf-8")
                    raw_path=RAW_DIR / f"{sid}_c{idx}.json"
                    if args.force or raw_requires_regeneration(raw_path, dry_run=args.dry_run, seed=args.seed):
                        print(f"[{position}/{total}] CALL  {sid} c{idx}: generating raw ({mode})", flush=True)
                        generate(brief,idx,args.seed,args.dry_run)
                    else:
                        print(f"[{position}/{total}] CALL  {sid} c{idx}: reusing compatible raw", flush=True)
                assembled=assemble(path,args.dry_run)
                if assembled.resolve() != output.resolve(): output=assembled
                print(f"[{position}/{total}] OK    {sid} output={output}", flush=True)
        except Exception as exc: status="failed"; error=str(exc)
        if status == "failed": print(f"[{position}/{total}] FAIL  {sid}: {error}", flush=True)
        entries.append({"brief_id":sid,"provider":"dry-run" if args.dry_run else PROVIDER,"prompt_version":PROMPT_VERSION,"model":"dry-run" if args.dry_run else MODEL,"seed":args.seed,"timestamp":datetime.now(timezone.utc).isoformat(),"status":status,"error":error})
    with manifest.open("w",encoding="utf-8") as f:
        for entry in entries: f.write(json.dumps(entry,ensure_ascii=False)+"\n")
    print(json.dumps({"status_counts":{s:sum(x["status"]==s for x in entries) for s in {x["status"] for x in entries}},"manifest":str(manifest)},ensure_ascii=False))


if __name__ == "__main__": main()
