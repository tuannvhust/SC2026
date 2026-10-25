"""Export all PostgreSQL/Supabase memory tables into a single Markdown file.

Target tables:
1. working_events
2. episodic_memory
3. profile_facts
4. profile_fact_history

Usage:
    python scripts/database/test_supabase_memory_dump.py
"""

from __future__ import annotations

import datetime
import decimal
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from dotenv import load_dotenv
from sqlalchemy import inspect, text

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Load project environment (.env)
load_dotenv(PROJECT_ROOT / ".env")

from src.memory.working.postgres_store import (
    default_database_url,
    describe_database_url,
    get_postgres_memory_store,
)

TARGET_TABLES = [
    "working_events",
    "episodic_memory",
    "profile_facts",
    "profile_fact_history",
]

AUDIT_SESSION_ID = "d33f2346-1bb3-4d4d-bce6-b749ee7a28dc"


class CustomJSONEncoder(json.JSONEncoder):
    """Safely format PostgreSQL/Python types into standard JSON."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        return super().default(obj)


def format_cell_json(val: Any) -> Any:
    """If a value is a JSON string (e.g. payload_json), try to parse it into nested dict/list for readability."""
    if isinstance(val, str):
        trimmed = val.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (
            trimmed.startswith("[") and trimmed.endswith("]")
        ):
            try:
                return json.loads(trimmed)
            except Exception:
                return val
    return val


def dump_memory_database(
    output_path: Path,
    target_session_id: Optional[str] = AUDIT_SESSION_ID,
) -> Tuple[str, Dict[str, Any]]:
    """Query Supabase memory tables in read-only transaction and dump Markdown."""
    start_time = datetime.datetime.now(datetime.timezone.utc)

    # 1. Check connection url
    try:
        raw_db_url = default_database_url()
        safe_url_desc = describe_database_url(raw_db_url)
    except Exception as exc:
        print("[MEMORY-DUMP] Database connection: FAILED")
        print(f"[MEMORY-DUMP] Error: {exc}")
        print("[MEMORY-DUMP] STATUS: FAIL")
        return "FAIL", {"error": str(exc)}

    # 2. Connect via project's PostgresMemoryStore
    try:
        store = get_postgres_memory_store()
        engine = store.engine
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        default_schema = inspector.default_schema_name or "public"
    except Exception as exc:
        print("[MEMORY-DUMP] Database connection: FAILED")
        print(f"[MEMORY-DUMP] Error: {exc}")
        print("[MEMORY-DUMP] STATUS: FAIL")
        return "FAIL", {"error": str(exc)}

    print("[MEMORY-DUMP] START")
    print("[MEMORY-DUMP] Database connection: SUCCESS")

    table_results: Dict[str, Dict[str, Any]] = {}
    total_rows_read = 0
    total_rows_exported = 0
    tables_found_count = 0
    tables_with_errors: List[str] = []

    # 3. Read tables in a transaction
    with engine.connect() as connection:
        # Use read-only transaction mode if postgresql
        if engine.dialect.name == "postgresql":
            try:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            except Exception:
                pass

        for table_name in TARGET_TABLES:
            if table_name not in existing_tables:
                table_results[table_name] = {
                    "status": "TABLE_NOT_FOUND",
                    "row_count": 0,
                    "columns": [],
                    "records": [],
                    "error": None,
                }
                tables_with_errors.append(table_name)
                print(f"[MEMORY-DUMP] {table_name}: TABLE_NOT_FOUND")
                continue

            tables_found_count += 1

            # Fetch columns schema
            try:
                columns_info = inspector.get_columns(table_name)
                cols_summary = [
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                    }
                    for col in columns_info
                ]
                pk_info = inspector.get_pk_constraint(table_name)
                pk_cols = pk_info.get("constrained_columns", []) if pk_info else []
            except Exception as schema_err:
                cols_summary = []
                pk_cols = []

            # Count rows
            try:
                count_res = connection.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                row_count = int(count_res or 0)
            except Exception as count_err:
                table_results[table_name] = {
                    "status": "READ_FAILED",
                    "row_count": -1,
                    "columns": cols_summary,
                    "records": [],
                    "error": str(count_err),
                }
                tables_with_errors.append(table_name)
                print(f"[MEMORY-DUMP] {table_name}: READ_FAILED ({count_err})")
                continue

            # Fetch all rows with stable ordering if PK exists
            order_clause = ""
            if pk_cols:
                order_cols = ", ".join(f'"{col}" ASC' for col in pk_cols)
                order_clause = f" ORDER BY {order_cols}"

            try:
                cursor = connection.execute(text(f'SELECT * FROM "{table_name}"{order_clause}'))
                records: List[Dict[str, Any]] = []
                for row in cursor.mappings():
                    # Parse each record, preserving all fields and nested structures
                    rec_dict = {}
                    for col_name, val in row.items():
                        rec_dict[col_name] = format_cell_json(val)
                    records.append(rec_dict)

                exported_count = len(records)
                total_rows_read += row_count
                total_rows_exported += exported_count

                table_results[table_name] = {
                    "status": "PASS" if exported_count == row_count else "MISMATCH",
                    "row_count": row_count,
                    "columns": cols_summary,
                    "records": records,
                    "primary_key": pk_cols,
                    "error": None,
                }
                print(f"[MEMORY-DUMP] {table_name}: rows={row_count} exported={exported_count}")
            except Exception as read_err:
                table_results[table_name] = {
                    "status": "READ_FAILED",
                    "row_count": row_count,
                    "columns": cols_summary,
                    "records": [],
                    "error": str(read_err),
                }
                tables_with_errors.append(table_name)
                print(f"[MEMORY-DUMP] {table_name}: READ_FAILED ({read_err})")

    # 4. Session correlation audit
    session_audit: Dict[str, Any] = {
        "target_session_id": target_session_id,
        "working_events": {"count": 0, "link_col": "session_id", "found": False},
        "episodic_memory": {"count": 0, "link_col": "session_id", "found": False},
        "profile_facts": {"count": 0, "link_col": "provenance_session_id", "found": False},
        "profile_fact_history": {"count": 0, "link_col": "provenance_session_id", "found": False},
    }

    if target_session_id:
        we_records = table_results.get("working_events", {}).get("records", [])
        we_matching = [r for r in we_records if r.get("session_id") == target_session_id]
        session_audit["working_events"]["count"] = len(we_matching)
        session_audit["working_events"]["found"] = len(we_matching) > 0

        ep_records = table_results.get("episodic_memory", {}).get("records", [])
        ep_matching = [r for r in ep_records if r.get("session_id") == target_session_id]
        session_audit["episodic_memory"]["count"] = len(ep_matching)
        session_audit["episodic_memory"]["found"] = len(ep_matching) > 0

        pf_records = table_results.get("profile_facts", {}).get("records", [])
        pf_matching = [r for r in pf_records if r.get("provenance_session_id") == target_session_id]
        session_audit["profile_facts"]["count"] = len(pf_matching)
        session_audit["profile_facts"]["found"] = len(pf_matching) > 0

        h_records = table_results.get("profile_fact_history", {}).get("records", [])
        h_matching = [r for r in h_records if r.get("provenance_session_id") == target_session_id]
        session_audit["profile_fact_history"]["count"] = len(h_matching)
        session_audit["profile_fact_history"]["found"] = len(h_matching) > 0

    # 5. Determine overall status
    if len(tables_with_errors) == 0 and tables_found_count == len(TARGET_TABLES):
        overall_status = "PASS"
    elif tables_found_count > 0:
        overall_status = "PARTIAL"
    else:
        overall_status = "FAIL"

    # 6. Generate single Markdown document
    end_time = datetime.datetime.now(datetime.timezone.utc)
    duration_sec = (end_time - start_time).total_seconds()

    md_lines: List[str] = []
    md_lines.append("# Supabase Memory Database Dump")
    md_lines.append("")
    md_lines.append(f"- Generated at: {start_time.isoformat()}")
    md_lines.append("- Database connection: SUCCESS")
    md_lines.append("- Read mode: read-only transaction")
    md_lines.append(f"- Overall status: {overall_status}")
    md_lines.append(f"- Duration: {duration_sec:.2f}s")
    md_lines.append("")
    md_lines.append("> [!NOTE]")
    md_lines.append("> File này được tạo tự động bởi `scripts/database/test_supabase_memory_dump.py` bằng kết nối trực tiếp đến PostgreSQL/Supabase thực tế của dự án. File chứa toàn bộ bản ghi và không được commit lên Git.")
    md_lines.append("")

    # Section 1: Database Connection
    md_lines.append("## 1. Database Connection")
    md_lines.append("")
    md_lines.append("- Connection status: Connected successfully via SQLAlchemy Engine")
    md_lines.append(f"- Database target: `{safe_url_desc}` (credentials stripped)")
    md_lines.append(f"- Schema inspected: `{default_schema}`")
    md_lines.append(f"- Query timestamp: `{start_time.isoformat()}`")
    md_lines.append("- Read isolation: Read-only transaction")
    md_lines.append("")

    # Section 2 - 5: Target tables
    section_num = 2
    for table_name in TARGET_TABLES:
        t_data = table_results.get(table_name, {})
        status = t_data.get("status", "UNKNOWN")
        row_count = t_data.get("row_count", 0)
        records = t_data.get("records", [])
        cols = t_data.get("columns", [])
        pk = t_data.get("primary_key", [])
        err = t_data.get("error")

        md_lines.append(f"## {section_num}. {table_name}")
        md_lines.append("")
        md_lines.append(f"- Table status: `{status}`")
        md_lines.append(f"- Row count (SELECT COUNT): {row_count}")
        md_lines.append(f"- Exported row count: {len(records)}")
        integrity = "PASS (row_count == exported_count)" if row_count == len(records) else "FAIL (mismatch)"
        if err:
            integrity = f"ERROR: {err}"
        md_lines.append(f"- Data integrity status: {integrity}")
        if pk:
            md_lines.append(f"- Primary key: `{', '.join(pk)}`")
        md_lines.append("")

        md_lines.append("### Column Schema")
        md_lines.append("")
        if cols:
            md_lines.append("| Column Name | Type | Nullable |")
            md_lines.append("|---|---|---|")
            for c in cols:
                md_lines.append(f"| `{c['name']}` | `{c['type']}` | {c['nullable']} |")
        else:
            md_lines.append("*Schema unavailable or table not found.*")
        md_lines.append("")

        md_lines.append("### Records")
        md_lines.append("")
        if err:
            md_lines.append(f"```text\nError reading table: {err}\n```")
        elif not records:
            md_lines.append("*Bảng hiện tại chưa có bản ghi nào (0 rows).*")
        else:
            md_lines.append(f"Tổng số bản ghi: **{len(records)}**")
            md_lines.append("")
            md_lines.append("```json")
            md_lines.append(json.dumps(records, ensure_ascii=False, indent=2, cls=CustomJSONEncoder))
            md_lines.append("```")
        md_lines.append("")
        section_num += 1

    # Section 6: Specific session audit
    md_lines.append(f"## {section_num}. Session Audit: `{target_session_id}`")
    md_lines.append("")
    md_lines.append("Kiểm tra đối chiếu session ID từ log hội thoại:")
    md_lines.append(f"- Target session ID: `{target_session_id}`")
    md_lines.append("")
    md_lines.append("| Bảng | Cột liên kết | Bản ghi tìm thấy | Trạng thái |")
    md_lines.append("|---|---|---|---|")

    for t_name, audit_info in session_audit.items():
        if t_name == "target_session_id":
            continue
        cnt = audit_info["count"]
        link = audit_info["link_col"]
        status_str = f"Found {cnt} rows" if cnt > 0 else "Not found (0 rows)"
        md_lines.append(f"| `{t_name}` | `{link}` | {cnt} | {status_str} |")

    md_lines.append("")
    md_lines.append("> [!IMPORTANT]")
    md_lines.append("> - Bảng `working_events` lưu lại từng lượt hội thoại (`turn`) thông qua `persist_turn_node`.")
    md_lines.append("> - Bảng `episodic_memory` chỉ được ghi khi phiên được kết thúc thành công qua `persist_call_node` (nút **Kết thúc phiên** hoặc sự kiện kết thúc cuộc gọi). Nếu phiên chưa được finalize hoặc bị lỗi ở bước finalize trước đó, `episodic_memory` sẽ có 0 bản ghi cho session này.")
    md_lines.append("> - Bảng `profile_facts` và `profile_fact_history` chỉ ghi nhận khi trong phiên có công cụ `memory.write` trích xuất thông tin khách hàng và session được kết thúc.")
    md_lines.append("")
    section_num += 1

    # Section 7: Summary
    md_lines.append(f"## {section_num}. Summary")
    md_lines.append("")
    md_lines.append(f"- Tables target: {len(TARGET_TABLES)}")
    md_lines.append(f"- Tables found: {tables_found_count}/{len(TARGET_TABLES)}")
    md_lines.append(f"- Tables successfully read: {len(TARGET_TABLES) - len(tables_with_errors)}/{len(TARGET_TABLES)}")
    md_lines.append(f"- Total rows read: {total_rows_read}")
    md_lines.append(f"- Total rows exported: {total_rows_exported}")
    md_lines.append(f"- Tables with errors: {len(tables_with_errors)} ({', '.join(tables_with_errors) if tables_with_errors else 'none'})")
    md_lines.append(f"- Final test status: **{overall_status}**")
    md_lines.append("")

    # Write to single markdown file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"[MEMORY-DUMP] Exported rows: {total_rows_exported}")
    print(f"[MEMORY-DUMP] Report: {output_path.resolve()}")
    print(f"[MEMORY-DUMP] STATUS: {overall_status}")
    print("[WARNING] Report contains real customer & conversation data. Do NOT commit or share publicly.")

    return overall_status, {
        "output_path": str(output_path.resolve()),
        "total_rows_read": total_rows_read,
        "total_rows_exported": total_rows_exported,
        "table_results": table_results,
        "session_audit": session_audit,
    }


if __name__ == "__main__":
    report_file = Path("supabase_memory_dump.md")
    status, meta = dump_memory_database(report_file)
    sys.exit(0 if status == "PASS" else 1)
