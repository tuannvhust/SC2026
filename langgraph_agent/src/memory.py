import hashlib
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Tuple


def get_db_path() -> str:
    return os.getenv("HARNESS_DB", "harness_memory.db")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers(
                customer_id TEXT PRIMARY KEY, phone_hash TEXT UNIQUE, created_at TEXT);
            CREATE TABLE IF NOT EXISTS profile(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT, slot TEXT, value TEXT,
                active INTEGER DEFAULT 1, updated_at TEXT, source_call_id TEXT);
            CREATE TABLE IF NOT EXISTS episodic(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT, call_id TEXT, ts TEXT, summary TEXT, outcome TEXT);
            CREATE TABLE IF NOT EXISTS knowledge_gaps(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT, call_id TEXT, question TEXT, ts TEXT, status TEXT DEFAULT 'open');
            CREATE TABLE IF NOT EXISTS orders(
                order_id TEXT PRIMARY KEY, customer_id TEXT, sku TEXT, price_vnd INTEGER, ts TEXT);
            """
        )


def _phone_hash(phone: str) -> str:
    # PII: không lưu số điện thoại thô trực tiếp, chỉ lưu chuỗi hash làm lookup key
    return hashlib.sha256(phone.strip().encode()).hexdigest()


def get_or_create_customer(phone: str) -> Tuple[str, bool]:
    h = _phone_hash(phone)
    with db() as c:
        row = c.execute("SELECT customer_id FROM customers WHERE phone_hash=?", (h,)).fetchone()
        if row:
            return row["customer_id"], True
        cid = "CUST-" + h[:8].upper()
        c.execute("INSERT INTO customers VALUES (?,?,?)", (cid, h, datetime.now().isoformat()))
        return cid, False


def load_profile(customer_id: str) -> Dict[str, Any]:
    with db() as c:
        rows = c.execute(
            "SELECT slot, value FROM profile WHERE customer_id=? AND active=1", (customer_id,)
        ).fetchall()
    return {r["slot"]: json.loads(r["value"]) for r in rows}


def upsert_slot(customer_id: str, slot: str, value: Any, call_id: str):
    """Mỗi (customer, slot) chỉ có duy nhất 1 dòng active=1. Nếu khách đổi ý => dòng cũ bị deactivate (active=0)."""
    new_val = json.dumps(value, ensure_ascii=False)
    with db() as c:
        cur = c.execute(
            "SELECT id, value FROM profile WHERE customer_id=? AND slot=? AND active=1",
            (customer_id, slot),
        ).fetchone()
        if cur and cur["value"] == new_val:
            return
        if cur:
            c.execute("UPDATE profile SET active=0 WHERE id=?", (cur["id"],))
        c.execute(
            "INSERT INTO profile(customer_id,slot,value,active,updated_at,source_call_id) VALUES (?,?,?,1,?,?)",
            (customer_id, slot, new_val, datetime.now().isoformat(), call_id),
        )


def load_episodic(customer_id: str, limit: int = 3) -> List[Dict[str, Any]]:
    with db() as c:
        rows = c.execute(
            "SELECT call_id, ts, summary, outcome FROM episodic WHERE customer_id=? ORDER BY id DESC LIMIT ?",
            (customer_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
