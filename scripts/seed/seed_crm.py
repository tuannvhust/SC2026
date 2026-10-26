
"""Seed CRM customers, orders and historical sessions.

Default mode is dry-run. Use --apply to write to Supabase PostgreSQL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.memory.ids import sync_id_sequences

load_dotenv(PROJECT_ROOT / ".env")

SEED_PATH = PROJECT_ROOT / "data" / "catalog" / "crm_seed.json"

REGIONS = {"bac", "trung", "nam"}
LEGACY_SESSION_ID_RENAMES = {
    "S-OLD-1": "S000001",
    "S-OLD-2": "S000002",
    "S-OLD-3": "S000003",
}

REQUIRED_COLUMNS = {
    "customers": {
        "customer_id", "full_name", "preferred_name", "honorific",
        "phone", "phone_verified", "zalo_id", "fb_id", "region",
        "status", "source", "deleted_at",
    },
    "orders": {
        "order_id", "customer_id", "order_date", "status",
        "tracking_number", "total_amount_vnd", "currency", "source_system",
    },
    "order_items": {
        "order_id", "line_number", "sku", "product_name_snapshot",
        "quantity", "unit_price_vnd", "line_total_vnd",
    },
    "conversation_sessions": {
        "session_id", "customer_id", "channel", "status",
        "started_at", "last_activity_at", "ended_at", "finalized_at",
        "outcome", "handoff_reason", "updated_at",
    },
    "episodic_memory": {
        "session_id", "customer_id", "summary", "outcome", "ended_at",
        "started_at", "handoff_reason", "products_advised", "orders_summary",
        "open_questions", "open_blockers", "next_actions", "source_event_ids",
        "turn_count", "payload_json", "updated_at",
    },
}


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _normalize_phone(raw):
    """Normalize Vietnamese phone numbers to 10 digits starting with 0."""
    if not raw:
        return None

    digits = re.sub(r"\D", "", str(raw))

    if digits.startswith("0084"):
        digits = "0" + digits[4:]
    elif digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]

    if not re.fullmatch(r"0\d{9}", digits):
        return None

    return digits


def _money(value, label):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label}: thiếu số tiền hợp lệ")

    try:
        amount = int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{label}: số tiền không hợp lệ") from exc

    if amount < 0:
        raise ValueError(f"{label}: số tiền không được âm")

    return amount


def _validate_date(value, label):
    value = _clean(value)
    if not value:
        raise ValueError(f"{label}: thiếu ngày")

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"{label}: ngày phải có định dạng YYYY-MM-DD"
        ) from exc

    return value


def load_seed():
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    customers = data.get("customers")

    if not isinstance(customers, list):
        raise ValueError("crm_seed.json phải chứa danh sách customers")

    return customers


def _build_plan():
    """Validate and normalize all seed rows before touching the database."""
    raw_customers = load_seed()

    customers = []
    orders = []
    sessions = []

    customer_ids = set()
    order_ids = set()
    session_ids = set()
    seen_zalo = {}
    seen_fb = {}

    for source in raw_customers:
        cid = _clean(source.get("customer_id"))
        if not cid:
            raise ValueError("Có customer thiếu customer_id")
        if cid in customer_ids:
            raise ValueError(f"customer_id bị trùng trong seed: {cid}")
        customer_ids.add(cid)

        name = _clean(source.get("name") or source.get("full_name"))
        preferred_name = _clean(source.get("preferred_name") or name)
        honorific = _clean(source.get("honorific"))
        phone_raw = _clean(source.get("phone"))
        phone = _normalize_phone(phone_raw)

        if phone_raw and not phone:
            raise ValueError(
                f"{cid}: số điện thoại không hợp lệ. "
                "Kiểm tra dữ liệu nguồn trước khi nạp."
            )

        region = _clean(source.get("region"))
        if region and region not in REGIONS:
            raise ValueError(
                f"{cid}: region phải thuộc {sorted(REGIONS)}, nhận được {region!r}"
            )

        customer = {
            "customer_id": cid,
            "full_name": name,
            "preferred_name": preferred_name,
            "honorific": honorific,
            "phone": phone,
            "phone_verified": False,
            "zalo_id": _clean(source.get("zalo_id")),
            "fb_id": _clean(source.get("fb_id")),
            "region": region,
            "status": "provisional",
            "source": "crm_seed",
        }

        for field, seen in (("zalo_id", seen_zalo), ("fb_id", seen_fb)):
            identity = customer[field]
            if identity:
                if identity in seen:
                    raise ValueError(
                        f"{field} bị trùng giữa {seen[identity]} và {cid}"
                    )
                seen[identity] = cid

        customers.append(customer)

        for order in source.get("orders") or []:
            oid = _clean(order.get("order_id"))
            if not oid:
                raise ValueError(f"{cid}: đơn hàng thiếu order_id")
            if oid in order_ids:
                raise ValueError(f"order_id bị trùng trong seed: {oid}")
            order_ids.add(oid)

            order_date = _validate_date(
                order.get("date") or order.get("order_date"),
                f"đơn {oid}",
            )
            status = _clean(order.get("status"))
            if not status:
                raise ValueError(f"đơn {oid}: thiếu status")

            total = _money(
                order.get("price_vnd", order.get("total_amount_vnd")),
                f"đơn {oid}",
            )

            # crm_seed.json hiện tại dùng trường sku đơn.
            # Chấp nhận skus nếu danh sách chỉ có một SKU.
            sku_value = order.get("sku")
            if sku_value is None:
                skus = order.get("skus")
                if isinstance(skus, list) and len(skus) == 1:
                    sku_value = skus[0]
                elif isinstance(skus, list) and len(skus) > 1:
                    raise ValueError(
                        f"đơn {oid} có nhiều SKU nhưng seed không có "
                        "giá từng dòng. Hãy bổ sung dữ liệu items trước khi nạp."
                    )

            sku = _clean(sku_value)
            if not sku:
                raise ValueError(f"đơn {oid}: thiếu sku")

            # Với schema nguồn hiện tại, mỗi đơn có một SKU và quantity = 1.
            orders.append({
                "order_id": oid,
                "customer_id": cid,
                "order_date": order_date,
                "status": status,
                "tracking_number": _clean(order.get("tracking")),
                "total_amount_vnd": total,
                "items": [{
                    "line_number": 1,
                    "sku": sku,
                    # The source contains SKU but no historical product name.
                    "product_name_snapshot": None,
                    "quantity": 1,
                    "unit_price_vnd": total,
                    "line_total_vnd": total,
                }],
            })

        for session in source.get("sessions") or []:
            sid = _clean(session.get("session_id"))
            if not sid:
                raise ValueError(f"{cid}: session thiếu session_id")
            if sid in session_ids:
                raise ValueError(f"session_id bị trùng trong seed: {sid}")
            session_ids.add(sid)

            session_date = _validate_date(
                session.get("date"), f"session {sid}"
            )
            sessions.append({
                "session_id": sid,
                "customer_id": cid,
                "channel": _clean(session.get("channel")) or "crm_seed",
                "date": session_date,
                "summary": _clean(session.get("summary"))
                    or "Seeded historical session.",
                "outcome": _clean(session.get("outcome")),
                "orders_summary": [
                    {
                        "order_id": _clean(order.get("order_id")),
                        "sku": _clean(order.get("sku")) or (
                            _clean(order.get("skus")[0])
                            if isinstance(order.get("skus"), list)
                            and len(order.get("skus")) == 1
                            else None
                        ),
                        "status": _clean(order.get("status")),
                    }
                    for order in (source.get("orders") or [])
                    if _validate_date(
                        order.get("date") or order.get("order_date"),
                        f"order {order.get('order_id')}"
                    ) == session_date
                ],
            })

    return customers, orders, sessions


def _check_schema(engine):
    """Fail before writes if migration 002 has not been applied correctly."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names(schema="public"))
    problems = []

    for table, required in REQUIRED_COLUMNS.items():
        if table not in existing_tables:
            problems.append(f"thiếu bảng public.{table}")
            continue

        actual = {
            column["name"]
            for column in inspector.get_columns(table, schema="public")
        }
        missing = sorted(required - actual)
        if missing:
            problems.append(
                f"public.{table} thiếu cột: {', '.join(missing)}"
            )

    if problems:
        raise RuntimeError(
            "Schema Supabase chưa sẵn sàng:\n- " + "\n- ".join(problems)
            + "\nHãy kiểm tra và áp dụng migration trước khi seed."
        )

    with engine.connect() as connection:
        missing_sequences = [
            name for name in (
                "customer_id_seq", "order_id_seq", "session_id_seq"
            )
            if connection.execute(
                text("SELECT to_regclass(:sequence_name)"),
                {"sequence_name": f"public.{name}"},
            ).scalar_one_or_none() is None
        ]
    if missing_sequences:
        raise RuntimeError(
            "Missing normalized ID sequences: " + ", ".join(missing_sequences)
            + ". Apply migration 003_record_id_sequences.sql first."
        )


def _check_conflicts(conn, customers, orders, sessions):
    """Check all known ID/data conflicts before any INSERT or UPDATE."""
    conflicts = []

    # Renaming these seed identifiers must not silently duplicate already
    # imported sessions or leave event/profile/checkpoint references behind.
    inspector = inspect(conn)
    tables = set(inspector.get_table_names(schema="public"))
    session_reference_columns = (
        ("conversation_sessions", "session_id"),
        ("working_events", "session_id"),
        ("episodic_memory", "session_id"),
        ("profile_facts", "source_session_id"),
        ("checkpoints", "thread_id"),
        ("checkpoint_writes", "thread_id"),
        ("checkpoint_blobs", "thread_id"),
    )
    for legacy_id, normalized_id in LEGACY_SESSION_ID_RENAMES.items():
        references = []
        for table, column in session_reference_columns:
            if table not in tables:
                continue
            available = {
                item["name"]
                for item in inspector.get_columns(table, schema="public")
            }
            if column not in available:
                continue
            found = conn.execute(
                text(f"SELECT 1 FROM public.{table} WHERE {column} = :sid LIMIT 1"),
                {"sid": legacy_id},
            ).first()
            if found:
                references.append(f"{table}.{column}")
        if references:
            conflicts.append(
                f"legacy session {legacy_id} -> {normalized_id} has existing references "
                f"({', '.join(references)}); reconcile with an explicit mapping first"
            )

    for customer in customers:
        cid = customer["customer_id"]
        existing = conn.execute(
            text("""
                SELECT customer_id, full_name, preferred_name, honorific,
                       phone, zalo_id, fb_id, region, status, deleted_at
                FROM public.customers
                WHERE customer_id = :cid
            """),
            {"cid": cid},
        ).mappings().first()

        if existing:
            if existing["deleted_at"] is not None or existing["status"] in {
                "deleted", "merged"
            }:
                conflicts.append(f"customer {cid}: bản ghi đang deleted/merged")
                continue

            compare_fields = (
                "full_name", "preferred_name", "honorific",
                "phone", "zalo_id", "fb_id", "region",
            )

            for field in compare_fields:
                old_value = _clean(existing[field])
                new_value = _clean(customer[field])

                if field == "phone" and old_value:
                    old_value = _normalize_phone(old_value) or old_value

                if old_value and new_value and old_value != new_value:
                    conflicts.append(f"customer {cid}: xung đột {field}")

        # phone không unique vì seed có khách hàng dùng chung số.
        # Zalo/Facebook được kiểm tra theo unique index của schema.
        for field in ("zalo_id", "fb_id"):
            identity = customer[field]
            if not identity:
                continue

            other = conn.execute(
                text(f"""
                    SELECT customer_id
                    FROM public.customers
                    WHERE {field} = :identity
                      AND customer_id <> :cid
                      AND deleted_at IS NULL
                    LIMIT 1
                """),
                {"identity": identity, "cid": cid},
            ).scalar()

            if other:
                conflicts.append(
                    f"customer {cid}: {field} đã thuộc customer {other}"
                )

    for order in orders:
        existing = conn.execute(
            text("""
                SELECT order_id, customer_id, order_date, status,
                       tracking_number, total_amount_vnd
                FROM public.orders
                WHERE order_id = :oid
            """),
            {"oid": order["order_id"]},
        ).mappings().first()

        if existing:
            old_date = str(existing["order_date"])
            expected = (
                order["customer_id"],
                order["order_date"],
                order["status"],
                order["tracking_number"],
                order["total_amount_vnd"],
            )
            actual = (
                existing["customer_id"],
                old_date,
                existing["status"],
                existing["tracking_number"],
                int(existing["total_amount_vnd"])
                    if existing["total_amount_vnd"] is not None else None,
            )
            if actual != expected:
                conflicts.append(
                    f"order {order['order_id']}: ID đã tồn tại với dữ liệu khác"
                )

        for item in order["items"]:
            existing_item = conn.execute(
                text("""
                    SELECT sku, product_name_snapshot, quantity,
                           unit_price_vnd, line_total_vnd
                    FROM public.order_items
                    WHERE order_id = :oid AND line_number = :line
                """),
                {
                    "oid": order["order_id"],
                    "line": item["line_number"],
                },
            ).mappings().first()

            if existing_item:
                actual = (
                    existing_item["sku"],
                    existing_item["product_name_snapshot"],
                    int(existing_item["quantity"]),
                    int(existing_item["unit_price_vnd"]),
                    int(existing_item["line_total_vnd"]),
                )
                expected = (
                    item["sku"],
                    item["product_name_snapshot"],
                    item["quantity"],
                    item["unit_price_vnd"],
                    item["line_total_vnd"],
                )
                if actual != expected:
                    conflicts.append(
                        f"order {order['order_id']}: dòng hàng "
                        f"{item['line_number']} có dữ liệu khác"
                    )

    for session in sessions:
        sid = session["session_id"]

        old_session_customer = conn.execute(
            text("""
                SELECT customer_id
                FROM public.conversation_sessions
                WHERE session_id = :sid
            """),
            {"sid": sid},
        ).scalar()

        if old_session_customer and old_session_customer != session["customer_id"]:
            conflicts.append(
                f"session {sid}: đang thuộc customer khác"
            )

        old_episode_customer = conn.execute(
            text("""
                SELECT customer_id
                FROM public.episodic_memory
                WHERE session_id = :sid
            """),
            {"sid": sid},
        ).scalar()

        if old_episode_customer and old_episode_customer != session["customer_id"]:
            conflicts.append(
                f"episode {sid}: đang thuộc customer khác"
            )

    if conflicts:
        details = "\n- ".join(conflicts[:30])
        more = (
            f"\n... còn {len(conflicts) - 30} xung đột khác"
            if len(conflicts) > 30 else ""
        )
        raise RuntimeError(
            "Preflight phát hiện xung đột. Chưa ghi dữ liệu nào.\n- "
            + details + more
        )


def _write_seed(conn, customers, orders, sessions):
    # Chỉ bổ sung trường còn trống. Không ghi đè thông tin hiện có.
    for customer in customers:
        conn.execute(
            text("""
                INSERT INTO public.customers (
                    customer_id, full_name, preferred_name, honorific,
                    phone, phone_verified, zalo_id, fb_id, region,
                    status, source
                ) VALUES (
                    :customer_id, :full_name, :preferred_name, :honorific,
                    :phone, :phone_verified, :zalo_id, :fb_id, :region,
                    :status, :source
                )
                ON CONFLICT (customer_id) DO UPDATE SET
                    full_name = COALESCE(
                        NULLIF(customers.full_name, ''),
                        EXCLUDED.full_name
                    ),
                    preferred_name = COALESCE(
                        NULLIF(customers.preferred_name, ''),
                        EXCLUDED.preferred_name
                    ),
                    honorific = COALESCE(
                        NULLIF(customers.honorific, ''),
                        EXCLUDED.honorific
                    ),
                    phone = COALESCE(
                        NULLIF(customers.phone, ''),
                        EXCLUDED.phone
                    ),
                    zalo_id = COALESCE(
                        NULLIF(customers.zalo_id, ''),
                        EXCLUDED.zalo_id
                    ),
                    fb_id = COALESCE(
                        NULLIF(customers.fb_id, ''),
                        EXCLUDED.fb_id
                    ),
                    region = COALESCE(
                        NULLIF(customers.region, ''),
                        EXCLUDED.region
                    ),
                    source = COALESCE(
                        NULLIF(customers.source, ''),
                        EXCLUDED.source
                    )
            """),
            customer,
        )

    for order in orders:
        conn.execute(
            text("""
                INSERT INTO public.orders (
                    order_id, customer_id, order_date, status,
                    tracking_number, total_amount_vnd, currency, source_system
                ) VALUES (
                    :order_id, :customer_id, CAST(:order_date AS DATE), :status,
                    :tracking_number, :total_amount_vnd, 'VND', 'crm_seed'
                )
                ON CONFLICT (order_id) DO NOTHING
            """),
            order,
        )

        for item in order["items"]:
            conn.execute(
                text("""
                    INSERT INTO public.order_items (
                        order_id, line_number, sku, product_name_snapshot,
                        quantity, unit_price_vnd, line_total_vnd
                    ) VALUES (
                        :order_id, :line_number, :sku, :product_name_snapshot,
                        :quantity, :unit_price_vnd, :line_total_vnd
                    )
                    ON CONFLICT (order_id, line_number) DO NOTHING
                """),
                {"order_id": order["order_id"], **item},
            )

    for session in sessions:
        timestamp = f'{session["date"]}T00:00:00+00:00'

        conn.execute(
            text("""
                INSERT INTO public.conversation_sessions (
                    session_id, customer_id, channel, status,
                    started_at, last_activity_at, ended_at, finalized_at,
                    outcome, updated_at
                ) VALUES (
                    :session_id, :customer_id, :channel, 'ended',
                    CAST(:ts AS TIMESTAMPTZ),
                    CAST(:ts AS TIMESTAMPTZ),
                    CAST(:ts AS TIMESTAMPTZ),
                    CAST(:ts AS TIMESTAMPTZ), :outcome, CAST(:ts AS TIMESTAMPTZ)
                )
                ON CONFLICT (session_id) DO UPDATE SET
                    customer_id = COALESCE(
                        conversation_sessions.customer_id,
                        EXCLUDED.customer_id
                    )
            """),
            {**session, "ts": timestamp},
        )

        conn.execute(
            text("""
                INSERT INTO public.episodic_memory (
                    session_id, customer_id, summary, outcome, ended_at,
                    started_at, handoff_reason, products_advised, orders_summary,
                    open_questions, open_blockers, next_actions,
                    source_event_ids, turn_count, payload_json, updated_at
                ) VALUES (
                    :session_id, :customer_id, :summary, :outcome,
                    CAST(:ts AS TIMESTAMPTZ), CAST(:ts AS TIMESTAMPTZ), NULL,
                    '[]'::jsonb, CAST(:orders_summary AS JSONB),
                    '[]'::jsonb, '[]'::jsonb,
                    '[]'::jsonb, '{}'::uuid[], 0,
                    jsonb_build_object('source', 'crm_seed', 'time_precision', 'day'),
                    CAST(:ts AS TIMESTAMPTZ)
                )
                ON CONFLICT (session_id) DO UPDATE SET
                    customer_id = COALESCE(
                        episodic_memory.customer_id,
                        EXCLUDED.customer_id
                    )
            """),
            {
                **session,
                "orders_summary": json.dumps(session["orders_summary"], ensure_ascii=False),
                "ts": timestamp,
            },
        )


def run(dry_run=True):
    customers, orders, sessions = _build_plan()
    item_count = sum(len(order["items"]) for order in orders)

    print(
        f"[SEED] customers={len(customers)} "
        f"orders={len(orders)} order_items={item_count} "
        f"sessions={len(sessions)}"
    )
    print(f"[SEED] mode={'dry-run (no writes)' if dry_run else 'apply'}")

    if dry_run:
        print("[SEED] Dữ liệu nguồn hợp lệ.")
        print("[SEED] Dry-run không kết nối DB và không ghi dữ liệu.")
        return 0

    from src.memory.working.postgres_store import (
        default_database_url,
        describe_database_url,
    )

    db_url = default_database_url()
    print(f"[SEED] Target: {describe_database_url(db_url)}")
    engine = create_engine(db_url)

    try:
        _check_schema(engine)

        # Toàn bộ preflight diễn ra trước INSERT/UPDATE.
        # Nếu gặp xung đột hoặc lỗi, transaction sẽ rollback.
        with engine.begin() as conn:
            _check_conflicts(conn, customers, orders, sessions)
            _write_seed(conn, customers, orders, sessions)
            sync_id_sequences(conn)

        print("[SEED] Transaction committed successfully.")
        print("[SEED] Hoàn tất. Hãy kiểm tra số lượng bản ghi trên Supabase.")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed CRM data to Supabase PostgreSQL"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Validate JSON only; this is the default",
    )
    mode.add_argument(
        "--apply", action="store_false", dest="dry_run",
        help="Validate and write to PostgreSQL",
    )
    parser.set_defaults(dry_run=True)
    args = parser.parse_args()

    try:
        sys.exit(run(dry_run=args.dry_run))
    except Exception as exc:
        print(
            f"[SEED][ERROR] {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
