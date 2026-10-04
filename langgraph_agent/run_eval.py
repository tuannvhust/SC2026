"""Run BTC public scenarios and emit the required JSONL trace.

Usage: python langgraph_agent/run_eval.py --scenarios data/test_set/public_sample --out trace.jsonl --config full
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import build_graph, handle_customer_turn  # noqa: E402


def run_file(path: Path, out: str, config: str) -> None:
    spec = json.loads(path.read_text(encoding="utf-8"))
    graph = build_graph()
    previous = date(2026, 10, 15)
    for call_name, call_spec in spec.get("calls", {}).items():
        call_date = date.fromisoformat(call_spec["call_date"]) if call_spec.get("call_date") else previous + timedelta(days=call_spec.get("days_later", 0))
        previous = call_date
        turns = call_spec.get("customer_turns_asr") if call_spec.get("customer_turns_asr") else call_spec.get("customer_turns", [])
        mode = call_spec.get("input_mode", "clean")
        for turn, text in enumerate(turns, 1):
            handle_customer_turn(
                graph, f"{spec['scenario_id']}-{call_name}", spec["customer_phone"],
                call_spec.get("channel", "hotline"), text,
                call_date=call_date.isoformat(), scenario_id=spec["scenario_id"], call=call_name,
                turn=turn, input_mode=mode, channel_identity=call_spec.get("channel_identity"),
                config=config, trace_path=out,
            )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", choices=("full", "baseline_no_memory"), default="full")
    args = ap.parse_args()
    Path(args.out).write_text("", encoding="utf-8")
    for path in sorted(Path(args.scenarios).glob("*.json")):
        run_file(path, args.out, args.config)


if __name__ == "__main__":
    main()
