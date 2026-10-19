"""Seed CRM customers, orders, and historical sessions (simplified schema)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

SEED_PATH = PROJECT_ROOT / "data" / "catalog" / "crm_seed.json"


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_seed_phone(raw):
    import re

    if not raw:
        return None
    digits = re.sub(r"[^\d+]", "", str(raw))
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    elif digits.startswith("84") and len(digits) > 9:
        digits = "0" + digits[2:]
    if not re.fullmatch(r"0\d{9}", digits or ""):
        return None
    return digits


def load_seed():
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return data.get("customers", [])


def run(dry_run: bool = True):
    customers = load_seed()
    n_orders = sum(len(c.get("orders") or []) for c in customers)
    n_sessions = sum(len(c.get("sessions") or []) for c in customers)
    print(f"[SEED] customers={len(customers)} orders={n_orders} sessions={n_sessions}")
    print(f"[SEED] mode={'dry-run (no writes)' if dry_run else 'apply'}")
    if dry_run:
        ids = [c.get("customer_id") for c in customers]
        assert len(ids) == len(set(ids)), "duplicate customer_id in seed"
        bad = [c.get("customer_id") for c in customers if not _normalize_seed_phone(c.get("phone"))]
        print(f"[SEED] invalid phones in seed: {len(bad)}")
        print("[SEED] dry-run ok, no rows written.")
        return 0
    from sqlalchemy import create_engine, text
    from src.memory.working.postgres_store import default_database_url, describe_database_url

    db_url = default_database_url()
    print(f"[SEED] target: {describe_database_url(db_url)}")
    engine = create_engine(db_url)
    conflicts = []
    inserted = {"customers": 0, "orders": 0, "items": 0, "sessions": 0, "episodes": 0}
    with engine.begin() as conn:
        for cust in customers:
            cid = cust.get("customer_id")
            row = {
                "customer_id": cid,
                "preferred_name": _clean(cust.get("name")),
                "honorific": _clean(cust.get("honorific")),
                "phone": _normalize_seed_phone(cust.get("phone")),
                "phone_verified": False,
                "zalo_id": _clean(cust.get("zalo_id")),
                "fb_id": _clean(cust.get("fb_id")),
                "region": _clean(cust.get("region")),
                "status": "provisional",
                "source": "crm_seed",
            }
            existing = conn.execute(
                text("SELECT customer_id, preferred_name, phone, zalo_id, fb_id, region FROM public.customers WHERE customer_id = :cid"),
                {"cid": cid},
            ).mappings().first()
            if existing:
                diff = [k for k in ("preferred_name", "phone", "zalo_id", "fb_id", "region") if (existing[k] or None) != (row[k] or None)]
                if diff:
                    conflicts.append(cid)
                    continue
            else:
                conn.execute(
                    text("INSERT INTO public.customers (customer_id, preferred_name, honorific, phone, phone_verified, zalo_id, fb_id, region, status, source) VALUES (:customer_id, :preferred_name, :honorific, :phone, :phone_verified, :zalo_id, :fb_id, :region, :status, :source) ON CONFLICT(customer_id) DO NOTHING"),
                    row,
                )
                inserted["customers"] += 1
            for order in cust.get("orders") or []:
                oid = order.get("order_id")
                if conn.execute(text("SELECT order_id FROM public.orders WHERE order_id = :oid"), {"oid": oid}).scalar():
                    continue
                conn.execute(
                    text("INSERT INTO public.orders (order_id, customer_id, order_date, status, tracking_number, total_amount_vnd, currency, source_system) VALUES (:order_id, :customer_id, CAST(:order_date AS DATE), :status, :tracking, :total, 'VND', 'crm_seed')"),
                    {"order_id": oid, "customer_id": cid, "order_date": order.get("date"), "status": order.get("status"), "tracking": order.get("tracking"), "total": order.get("price_vnd")},
                )
                inserted["orders"] += 1
                line_no = 0
                for sku in order.get("skus") or []:
                    line_no += 1
                    conn.execute(
                        text("INSERT INTO public.order_items (order_id, line_number, sku, product_name_snapshot, quantity, unit_price_vnd, line_total_vnd) VALUES (:order_id, :line_number, :sku, :sku, 1, :unit_price, :line_total) ON CONFLICT(order_id, line_number) DO NOTHING"),
                        {"order_id": oid, "line_number": line_no, "sku": sku, "unit_price": order.get("price_vnd") or 0, "line_total": order.get("price_vnd") or 0},
                    )
                    inserted["items"] += 1
            for sess in cust.get("sessions") or []:
                sid = sess.get("session_id")
                ts = f"{sess.get('date')}T00:00:00+00:00"
                if not conn.execute(text("SELECT session_id FROM public.conversation_sessions WHERE session_id = :sid"), {"sid": sid}).scalar():
                    conn.execute(
                        text("INSERT INTO public.conversation_sessions (session_id, customer_id, channel, status, started_at, last_activity_at, ended_at, outcome) VALUES (:sid, :cid, 'crm_seed', 'ended', CAST(:ts AS TIMESTAMPTZ), CAST(:ts AS TIMESTAMPTZ), CAST(:ts AS TIMESTAMPTZ), :outcome)"),
                        {"sid": sid, "cid": cid, "ts": ts, "outcome": sess.get("outcome")},
                    )
                    inserted["sessions"] += 1
                if not conn.execute(text("SELECT session_id FROM public.episodic_memory WHERE session_id = :sid"), {"sid": sid}).scalar():
                    conn.execute(
                        text("INSERT INTO public.episodic_memory (session_id, customer_id, summary, outcome, ended_at) VALUES (:sid, :cid, :summary, :outcome, CAST(:ts AS TIMESTAMPTZ))"),
                        {"sid": sid, "cid": cid, "summary": sess.get("summary") or "Seeded historical session.", "outcome": sess.get("outcome"), "ts": ts},
                    )
                    inserted["episodes"] += 1
    print(f"[SEED] inserted={inserted} conflicts={len(conflicts)} ids={conflicts}")
    return 2 if conflicts else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(run(dry_run=not args.apply))
