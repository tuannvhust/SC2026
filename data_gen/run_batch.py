from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .assemble_scenario import run as assemble
from .config import FACT_PACKS_DIR, MODEL, PROMPT_VERSION, REPORTS_DIR, RAW_DIR, SCENARIOS_DIR
from .gen_dialogue import run as generate
from .facts import build_fact_pack


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--briefs",default=str(Path(__file__).parent / "briefs")); ap.add_argument("--out",default=str(SCENARIOS_DIR)); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--limit",type=int); ap.add_argument("--force",action="store_true"); ap.add_argument("--seed",type=int,default=7); args=ap.parse_args()
    out_dir=Path(args.out); out_dir.mkdir(exist_ok=True); manifest=REPORTS_DIR / "manifest.jsonl"; entries=[]
    paths=sorted(Path(args.briefs).glob("*.json")); paths=paths[:args.limit] if args.limit else paths
    for path in paths:
        brief=json.loads(path.read_text(encoding="utf-8")); sid=brief["brief_id"]; output=out_dir / f"{sid}.json"; status="ok"; error=None
        try:
            if output.exists() and not args.force: status="skipped"
            else:
                for call in brief["calls"]:
                    idx=call["call_index"]
                    pack_path=FACT_PACKS_DIR / f"{sid}_c{idx}.json"
                    if args.force or not pack_path.exists(): pack_path.write_text(json.dumps(build_fact_pack(brief,idx),ensure_ascii=False,indent=2),encoding="utf-8")
                    raw_path=RAW_DIR / f"{sid}_c{idx}.json"
                    if args.force or not raw_path.exists(): generate(brief,idx,args.seed,args.dry_run)
                assembled=assemble(path,args.dry_run)
                if assembled.resolve() != output.resolve(): output=assembled
        except Exception as exc: status="failed"; error=str(exc)
        entries.append({"brief_id":sid,"prompt_version":PROMPT_VERSION,"model":"dry-run" if args.dry_run else MODEL,"seed":args.seed,"timestamp":datetime.now(timezone.utc).isoformat(),"status":status,"error":error})
    with manifest.open("w",encoding="utf-8") as f:
        for entry in entries: f.write(json.dumps(entry,ensure_ascii=False)+"\n")
    print(json.dumps({"status_counts":{s:sum(x["status"]==s for x in entries) for s in {x["status"] for x in entries}},"manifest":str(manifest)},ensure_ascii=False))


if __name__ == "__main__": main()
