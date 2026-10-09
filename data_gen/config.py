from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BTC_DIR = Path(os.getenv("BTC_DIR", str(ROOT / "data"))).resolve()
DATA_GEN_DIR = Path(__file__).resolve().parent
BRIEFS_DIR = DATA_GEN_DIR / "briefs"
FACT_PACKS_DIR = DATA_GEN_DIR / "fact_packs"
RAW_DIR = DATA_GEN_DIR / "raw"
SCENARIOS_DIR = DATA_GEN_DIR / "scenarios"
DRYRUN_DIR = DATA_GEN_DIR / "scenarios_dryrun"
REPORTS_DIR = DATA_GEN_DIR / "reports"
MODEL = os.getenv("HARNESS_GEN_MODEL", os.getenv("HARNESS_MODEL", "claude-sonnet-4-6"))
PROMPT_VERSION = "dialogue_v1"
REFERENCE_DATE = "2026-10-15"

for _directory in (BRIEFS_DIR, FACT_PACKS_DIR, RAW_DIR, SCENARIOS_DIR, DRYRUN_DIR, REPORTS_DIR):
    _directory.mkdir(exist_ok=True)


def json_path(relative: str) -> Path:
    return BTC_DIR / relative
