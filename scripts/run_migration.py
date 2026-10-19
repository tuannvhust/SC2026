"""Run versioned SQL migrations against configured Supabase project.

Usage:
    python scripts/run_migration.py [--rollback]

Safety:
    - No automatic DROP / TRUNCATE / data deletion before running migrations.
    - If v1 tables already exist, the runner stops and reports the migration
      status as unverified instead of silently re-applying DDL.
    - SQLAlchemy ``connect()`` is used (not ``begin()``) so the SQL file's own
      BEGIN/COMMIT is not wrapped in a nested transaction.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from src.memory.working.postgres_store import (
    default_database_url,
    describe_database_url,
)
from sqlalchemy import inspect, text

# Simplified target tables (14) per docs/SC2026_database_schema_simplified.md.
SIMPLIFIED_TABLES = (
    "customers",
    "orders",
    "order_items",
    "conversation_sessions",
    "working_events",
    "profile_facts",
    "episodic_memory",
    "products",
    "product_variants",
    "promotions",
    "checkpoints",
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoint_migrations",
)

# Legacy tables removed from the active schema (drops stay gated in 002).
LEGACY_TABLES = (
    "customer_identities",
    "customer_addresses",
    "profile_fact_candidates",
    "profile_fact_history",
)


def _apply_sql_file(engine, sql_file: Path, label: str) -> None:
    print(f"[MIGRATION] Applying {label}: {sql_file.name}")
    sql_content = sql_file.read_text(encoding="utf-8")
    # Use connect() instead of begin() so the SQL file's own BEGIN/COMMIT is
    # not wrapped in a SQLAlchemy nested transaction.
    with engine.connect() as connection:
        connection.execute(text(sql_content))
        connection.commit()


def run_migration(rollback: bool = False):
    db_url = default_database_url()
    print(f"[MIGRATION] Target database: {describe_database_url(db_url)}")

    migration_dir = PROJECT_ROOT / "src" / "memory" / "migrations"
    sequence = ["002_simplified_schema", "001_schema_v1"] if rollback else ["001_schema_v1", "002_simplified_schema"]

    from sqlalchemy import create_engine
    engine = create_engine(db_url)

    if rollback:
        print("[MIGRATION] WARNING: rollback requested — additive 002 reverted first, then v1.")
    for name in sequence:
        suffix = "_rollback.sql" if rollback else ".sql"
        sql_file = migration_dir / f"{name}{suffix}"
        if not sql_file.exists():
            print(f"[MIGRATION] File not found: {sql_file}")
            sys.exit(1)
        _apply_sql_file(engine, sql_file, "rollback" if rollback else "migration")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = [t for t in SIMPLIFIED_TABLES if t not in tables]
    legacy = [t for t in LEGACY_TABLES if t in tables]
    print("[MIGRATION] Successfully executed!")
    print(f"[MIGRATION] Current tables in public schema: {sorted(tables)}")
    if not rollback:
        print(f"[MIGRATION] Missing simplified tables: {missing or 'none'}")
        print(f"[MIGRATION] Legacy tables still present (gated drops): {legacy or 'none'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true", help="Rollback schema v1")
    args = parser.parse_args()
    run_migration(rollback=args.rollback)
