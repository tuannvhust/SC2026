from __future__ import annotations

import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)  # Load .env from current working directory for pytest

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
BTC_DIR = Path(os.getenv("BTC_DIR", str(ROOT / "data"))).resolve()
DATA_GEN_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = DATA_GEN_DIR / "prompts"
SCHEMAS_DIR = DATA_GEN_DIR / "schemas"
COVERAGE_MATRIX_PATH = DATA_GEN_DIR / "coverage_matrix" / "coverage_matrix.csv"
OUTPUT_DIR = DATA_GEN_DIR.parent / "generated" / "scenario-dataset"
BRIEFS_DIR = OUTPUT_DIR / "briefs"
FACT_PACKS_DIR = OUTPUT_DIR / "fact_packs"
RAW_DIR = OUTPUT_DIR / "raw"
SCENARIOS_DIR = OUTPUT_DIR / "scenarios"
DRYRUN_DIR = OUTPUT_DIR / "scenarios_dryrun"
REPORTS_DIR = OUTPUT_DIR / "reports"
DATASET_CONFIG = DATA_GEN_DIR / "dataset_config.json"
PROVIDER = "gemini"
MODEL = os.getenv("HARNESS_GEN_MODEL", os.getenv("HARNESS_MODEL", "gemini-2.5-flash"))
PROMPT_VERSION = "customer_turns_v5"
REFERENCE_DATE = "2026-10-15"

for _directory in (BRIEFS_DIR, FACT_PACKS_DIR, RAW_DIR, SCENARIOS_DIR, DRYRUN_DIR, REPORTS_DIR):
    _directory.mkdir(parents=True, exist_ok=True)


def json_path(relative: str) -> Path:
    return BTC_DIR / relative


def load_dataset_config() -> dict:
    return json.loads(DATASET_CONFIG.read_text(encoding="utf-8"))
