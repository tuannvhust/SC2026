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

# v1 business tables that must exist for schema v1 to be considered applied.
V1_TABLES = (
    "customers",
    "customer_identities",
    "customer_addresses",
    "conversation_sessions",
    "working_events",
    "profile_fact_candidates",
    "profile_facts",
    "profile_fact_history",
    "episodic_memory",
)


def run_migration(rollback: bool = False):
    db_url = default_database_url()
    print(f"[MIGRATION] Target database: {describe_database_url(db_url)}")

    migration_dir = PROJECT_ROOT / "src" / "memory" / "migrations"
    sql_file = (
        migration_dir / "001_schema_v1_rollback.sql"
        if rollback
        else migration_dir / "001_schema_v1.sql"
    )

    if not sql_file.exists():
        print(f"[MIGRATION] File not found: {sql_file}")
        sys.exit(1)

    from sqlalchemy import create_engine
    engine = create_engine(db_url)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if not rollback:
        missing_v1 = [t for t in V1_TABLES if t not in existing_tables]
        if not missing_v1:
            print("[MIGRATION] All v1 tables already exist in the target database.")
            print(
                "[MIGRATION] Migration history cannot be verified from this runner "
                "alone (no schema_migrations table is managed here). "
                "Aborting to avoid re-applying DDL."
            )
            print("[MIGRATION] Status: UNVERIFIED — no changes made.")
            sys.exit(0)

    print(f"[MIGRATION] Applying: {sql_file.name}")
    sql_content = sql_file.read_text(encoding="utf-8")

    # Use connect() instead of begin() so the SQL file's own BEGIN/COMMIT is
    # not wrapped in a SQLAlchemy nested transaction.
    with engine.connect() as connection:
        if rollback:
            print("[MIGRATION] WARNING: rollback requested — proceeding with rollback SQL.")
        connection.execute(text(sql_content))
        connection.commit()

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print("[MIGRATION] Successfully executed!")
    print(f"[MIGRATION] Current tables in public schema: {tables}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true", help="Rollback schema v1")
    args = parser.parse_args()
    run_migration(rollback=args.rollback)
