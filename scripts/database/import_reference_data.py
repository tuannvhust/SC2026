"""Nạp catalog và metadata chính sách vào Postgres local.

Đọc ``data/catalog`` và ``data/policy``. Không sửa file nguồn.

Usage:
    python scripts/database/import_reference_data.py --dry-run
    python scripts/database/import_reference_data.py --write-seed
    python scripts/database/import_reference_data.py

Script chỉ ghi khi ``SUPABASE_DATABASE_URL`` trỏ ``127.0.0.1`` hoặc
``localhost``. Thêm ``--allow-remote`` mới được ghi vào host khác.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Ngày hiệu lực lấy từ tiêu đề tài liệu và changelog BTC.
# Nội dung markdown không có cột trong schema hiện tại.
POLICY_VERSIONS: dict[str, dict[str, str | None]] = {
    "chinh-sach-bao-hanh.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "chinh-sach-doi-tra.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "chinh-sach-doi-tra-v2026-06-HET-HIEU-LUC.md": {
        "visibility": "expired",
        "effective_from": "2026-06-01",
        "effective_to": "2026-09-30",
    },
    "chinh-sach-van-chuyen-thanh-toan.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "changelog.md": {
        "visibility": "agent",
        "effective_from": "2026-06-01",
        "effective_to": None,
    },
    "dieu-khoan-khuyen-mai.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "faq.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "ghi-chu-nhap-hang-NOI-BO.md": {
        "visibility": "internal",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "noi-quy-nhan-vien.md": {
        "visibility": "internal",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "playbook-telesale.md": {
        "visibility": "agent",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "quy-trinh-cod-hoan-hang.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "spec-gia-dung.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "spec-thoi-trang-me-be.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
    "thong-bao-lich-nghi.md": {
        "visibility": "customer",
        "effective_from": "2026-10-01",
        "effective_to": None,
    },
}


@dataclass
class ImportPlan:
    """Các dòng sẽ ghi, và các dòng nguồn không có chỗ trong schema."""

    products: list[dict] = field(default_factory=list)
    variants: list[dict] = field(default_factory=list)
    promotions: list[dict] = field(default_factory=list)
    promotion_products: list[dict] = field(default_factory=list)
    inventory: list[dict] = field(default_factory=list)
    customers: list[dict] = field(default_factory=list)
    sessions: list[dict] = field(default_factory=list)
    episodes: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    order_items: list[dict] = field(default_factory=list)
    policies: list[dict] = field(default_factory=list)
    policy_versions: list[dict] = field(default_factory=list)
    skipped_inventory: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def promotion_target(token: str) -> tuple[str, str]:
    """Đổi một phần tử ``applies_to`` sang ``promotion_products``."""
    if token == "*":
        return "all", "all"
    if token.startswith("category:"):
        return "category", token.split(":", 1)[1]
    return "sku", token


def markdown_title(text: str) -> str:
    """Lấy heading đầu tiên, bỏ ký hiệu markdown."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").replace("**", "").strip()
    return ""


def is_local_database(database_url: str) -> bool:
    """Host local là đích an toàn mặc định của importer."""
    host = (make_url(database_url).host or "").lower()
    return host in LOCAL_HOSTS


def describe_target(database_url: str) -> str:
    """Host, cổng và tên database, không gồm mật khẩu."""
    url = make_url(database_url)
    return f"{url.host}:{url.port}/{url.database}"


def _blank_to_none(value: object) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_plan(data_dir: Path) -> ImportPlan:
    """Đọc catalog và policy thành dòng sẵn sàng ghi."""
    plan = ImportPlan()
    products_doc = _load_json(data_dir / "catalog" / "products.json")
    promotions_doc = _load_json(data_dir / "catalog" / "promotions.json")
    inventory_doc = _load_json(data_dir / "catalog" / "inventory_timeline.json")
    crm_doc = _load_json(data_dir / "catalog" / "crm_seed.json")

    product_skus: set[str] = set()
    variant_skus: set[str] = set()
    for product in products_doc["products"]:
        sku = product["sku"]
        product_skus.add(sku)
        plan.products.append(
            {
                "sku": sku,
                "name": product["name"],
                "category": product.get("category"),
                "brand": product.get("brand"),
                "list_price_vnd": product.get("list_price_vnd"),
                "attributes": json.dumps(product.get("attributes") or {}, ensure_ascii=False),
                "stock": product.get("stock") or 0,
            }
        )
        for variant in product.get("variants") or []:
            variant_sku = variant["variant_sku"]
            variant_skus.add(variant_sku)
            size = variant.get("size")
            plan.variants.append(
                {
                    "variant_sku": variant_sku,
                    "product_sku": sku,
                    "size": None if size is None else str(size),
                    "color": variant.get("color"),
                    "price_delta_vnd": variant.get("price_delta_vnd") or 0,
                    "stock": variant.get("stock") or 0,
                }
            )

    for promo in promotions_doc["promotions"]:
        code = promo["promo_code"]
        gift_sku = promo.get("gift_sku")
        if gift_sku and gift_sku not in product_skus:
            plan.errors.append(f"Khuyến mãi {code} trỏ gift_sku không có trong catalog: {gift_sku}")
        plan.promotions.append(
            {
                "promo_code": code,
                "name": promo["name"],
                "type": promo["type"],
                "starts_on": promo.get("start"),
                "ends_on": promo.get("end"),
                "stackable": bool(promo.get("stackable")),
                "discount_vnd": promo.get("discount_vnd"),
                "discount_percent": promo.get("discount_percent"),
                "gift_sku": gift_sku,
                "min_order_vnd": promo.get("min_order_vnd"),
                "conditions": json.dumps(promo.get("conditions") or {}, ensure_ascii=False),
            }
        )
        for token in promo.get("applies_to") or []:
            target_type, target_value = promotion_target(token)
            plan.promotion_products.append(
                {
                    "promo_code": code,
                    "target_type": target_type,
                    "target_value": target_value,
                }
            )

    for event in inventory_doc["events"]:
        raw_sku = event["sku"]
        row = {
            "sku": None,
            "variant_sku": None,
            "observed_on": event["date"],
            "quantity": event["qty"],
        }
        if raw_sku in variant_skus:
            row["variant_sku"] = raw_sku
        elif raw_sku in product_skus:
            row["sku"] = raw_sku
        else:
            plan.skipped_inventory.append(raw_sku)
            continue
        plan.inventory.append(row)

    seen_zalo: dict[str, str] = {}
    seen_fb: dict[str, str] = {}
    for customer in crm_doc["customers"]:
        customer_id = customer["customer_id"]
        zalo_id = _blank_to_none(customer.get("zalo_id"))
        fb_id = _blank_to_none(customer.get("fb_id"))
        if zalo_id:
            previous = seen_zalo.get(zalo_id)
            if previous:
                plan.errors.append(f"zalo_id {zalo_id} trùng {previous} và {customer_id}")
            seen_zalo[zalo_id] = customer_id
        if fb_id:
            previous = seen_fb.get(fb_id)
            if previous:
                plan.errors.append(f"fb_id {fb_id} trùng {previous} và {customer_id}")
            seen_fb[fb_id] = customer_id
        plan.customers.append(
            {
                "customer_id": customer_id,
                "name": customer.get("name"),
                "honorific": customer.get("honorific"),
                "status": "active",
                "phone": _blank_to_none(customer.get("phone")),
                "zalo_id": zalo_id,
                "fb_id": fb_id,
                "region": customer.get("region"),
            }
        )
        sessions_on_date: dict[tuple[str, str], list[str]] = {}
        for session in customer.get("sessions") or []:
            session_id = session.get("session_id")
            call_date = session.get("date")
            if not session_id or not call_date:
                plan.errors.append(f"Session của {customer_id} thiếu session_id hoặc date")
                continue
            started_at = f"{call_date}T00:00:00Z"
            plan.sessions.append(
                {
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "channel": session.get("channel"),
                    "call_date": call_date,
                    "status": "ended",
                    "outcome": session.get("outcome"),
                    "started_at": started_at,
                    "ended_at": started_at,
                }
            )
            plan.episodes.append(
                {
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "summary_masked": session.get("summary"),
                    "generated_at": started_at,
                }
            )
            sessions_on_date.setdefault((customer_id, call_date), []).append(session_id)
        for order in customer.get("orders") or []:
            order_id = order.get("order_id")
            price_vnd = order.get("price_vnd")
            if not order_id or price_vnd is None or not order.get("sku") or not order.get("date"):
                plan.errors.append(f"Đơn của {customer_id} thiếu order_id, sku, price_vnd hoặc date")
                continue
            matches = sessions_on_date.get((customer_id, order["date"]), [])
            plan.orders.append(
                {
                    "order_id": order_id,
                    "tracking": order.get("tracking"),
                    "customer_id": customer_id,
                    "source_session_id": matches[0] if len(matches) == 1 else None,
                    "status": order.get("status"),
                    "total_vnd": price_vnd,
                    "order_date": order["date"],
                }
            )
            plan.order_items.append(
                {
                    "order_id": order_id,
                    "sku": order["sku"],
                    "quantity": 1,
                    "unit_price_vnd": price_vnd,
                    "line_total_vnd": price_vnd,
                    "product_snapshot": json.dumps(
                        {"sku": order["sku"], "price_vnd": price_vnd, "quantity_assumed": 1},
                        ensure_ascii=False,
                    ),
                }
            )

    policy_dir = data_dir / "policy"
    for path in sorted(policy_dir.glob("*.md")):
        meta = POLICY_VERSIONS.get(path.name)
        if meta is None:
            plan.errors.append(f"Chưa khai báo ngày hiệu lực cho {path.name}")
            continue
        policy_id = path.stem
        title = markdown_title(path.read_text(encoding="utf-8")) or policy_id
        plan.policies.append(
            {
                "policy_id": policy_id,
                "title": title,
                "visibility": meta["visibility"],
            }
        )
        plan.policy_versions.append(
            {
                "policy_id": policy_id,
                "effective_from": meta["effective_from"],
                "effective_to": meta["effective_to"],
            }
        )
    return plan


def format_plan(plan: ImportPlan) -> str:
    """Tóm tắt để đọc trước khi ghi."""
    lines = [
        f"products: {len(plan.products)}",
        f"product_variants: {len(plan.variants)}",
        f"promotions: {len(plan.promotions)}",
        f"promotion_products: {len(plan.promotion_products)}",
        f"inventory_snapshots: {len(plan.inventory)}",
        f"customers: {len(plan.customers)}",
        f"conversation_sessions: {len(plan.sessions)}",
        f"episodes: {len(plan.episodes)}",
        f"orders: {len(plan.orders)}",
        f"order_items: {len(plan.order_items)}",
        f"policies: {len(plan.policies)}",
        f"policy_versions: {len(plan.policy_versions)}",
        f"skipped_inventory: {len(plan.skipped_inventory)} ({', '.join(plan.skipped_inventory) or 'none'})",
        "order_quantity: crm seed không có số lượng; mỗi đơn được ghi quantity = 1.",
        "session_summary: ghi vào episodes.summary_masked. started_at là 00:00 UTC của ngày seed.",
        "policy_body: không ghi. Bảng policies chỉ có policy_id, title, visibility.",
        "inventory_note: không ghi. Bảng inventory_snapshots không có cột note.",
    ]
    if plan.errors:
        lines.append("errors:")
        lines.extend(f"- {error}" for error in plan.errors)
    return "\n".join(lines)


def _engine_url(database_url: str):
    url = make_url(database_url)
    if is_local_database(database_url):
        query = dict(url.query)
        query["sslmode"] = "disable"
        url = url.set(query=query)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg2")
    return url


def apply_plan(connection: Connection, plan: ImportPlan) -> None:
    """Ghi plan trong transaction của caller."""
    connection.execute(
        text(
            """
            INSERT INTO public.products (
                sku, name, category, brand, list_price_vnd, attributes, stock
            )
            VALUES (
                :sku, :name, :category, :brand, :list_price_vnd,
                CAST(:attributes AS jsonb), :stock
            )
            ON CONFLICT (sku) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                brand = EXCLUDED.brand,
                list_price_vnd = EXCLUDED.list_price_vnd,
                attributes = EXCLUDED.attributes,
                stock = EXCLUDED.stock,
                updated_at = now()
            """
        ),
        plan.products,
    )
    if plan.variants:
        connection.execute(
            text(
                """
                INSERT INTO public.product_variants (
                    variant_sku, product_sku, size, color, price_delta_vnd, stock
                )
                VALUES (
                    :variant_sku, :product_sku, :size, :color, :price_delta_vnd, :stock
                )
                ON CONFLICT (variant_sku) DO UPDATE SET
                    product_sku = EXCLUDED.product_sku,
                    size = EXCLUDED.size,
                    color = EXCLUDED.color,
                    price_delta_vnd = EXCLUDED.price_delta_vnd,
                    stock = EXCLUDED.stock
                """
            ),
            plan.variants,
        )
    connection.execute(
        text(
            """
            INSERT INTO public.promotions (
                promo_code, name, type, starts_on, ends_on, stackable,
                discount_vnd, discount_percent, gift_sku, min_order_vnd, conditions
            )
            VALUES (
                :promo_code, :name, :type, :starts_on, :ends_on, :stackable,
                :discount_vnd, :discount_percent, :gift_sku, :min_order_vnd,
                CAST(:conditions AS jsonb)
            )
            ON CONFLICT (promo_code) DO UPDATE SET
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                starts_on = EXCLUDED.starts_on,
                ends_on = EXCLUDED.ends_on,
                stackable = EXCLUDED.stackable,
                discount_vnd = EXCLUDED.discount_vnd,
                discount_percent = EXCLUDED.discount_percent,
                gift_sku = EXCLUDED.gift_sku,
                min_order_vnd = EXCLUDED.min_order_vnd,
                conditions = EXCLUDED.conditions
            """
        ),
        plan.promotions,
    )
    promo_codes = [{"promo_code": row["promo_code"]} for row in plan.promotions]
    connection.execute(
        text("DELETE FROM public.promotion_products WHERE promo_code = :promo_code"),
        promo_codes,
    )
    if plan.promotion_products:
        connection.execute(
            text(
                """
                INSERT INTO public.promotion_products (promo_code, target_type, target_value)
                VALUES (:promo_code, :target_type, :target_value)
                """
            ),
            plan.promotion_products,
        )
    for row in plan.inventory:
        if row["variant_sku"]:
            connection.execute(
                text(
                    """
                    DELETE FROM public.inventory_snapshots
                    WHERE variant_sku = :variant_sku AND observed_on = :observed_on
                    """
                ),
                row,
            )
        else:
            connection.execute(
                text(
                    """
                    DELETE FROM public.inventory_snapshots
                    WHERE sku = :sku AND variant_sku IS NULL AND observed_on = :observed_on
                    """
                ),
                row,
            )
    if plan.inventory:
        connection.execute(
            text(
                """
                INSERT INTO public.inventory_snapshots (sku, variant_sku, observed_on, quantity)
                VALUES (:sku, :variant_sku, :observed_on, :quantity)
                """
            ),
            plan.inventory,
        )
    connection.execute(
        text(
            """
            INSERT INTO public.customers (
                customer_id, name, honorific, status, phone, zalo_id, fb_id, region
            )
            VALUES (
                :customer_id, :name, :honorific, :status, :phone, :zalo_id, :fb_id, :region
            )
            ON CONFLICT (customer_id) DO UPDATE SET
                name = EXCLUDED.name,
                honorific = EXCLUDED.honorific,
                status = EXCLUDED.status,
                phone = EXCLUDED.phone,
                zalo_id = EXCLUDED.zalo_id,
                fb_id = EXCLUDED.fb_id,
                region = EXCLUDED.region,
                updated_at = now()
            """
        ),
            plan.customers,
    )
    if plan.sessions:
        connection.execute(
            text(
                """
                INSERT INTO public.conversation_sessions (
                    session_id, customer_id, channel, call_date, status, outcome,
                    started_at, ended_at
                )
                VALUES (
                    :session_id, :customer_id, :channel, :call_date, :status, :outcome,
                    :started_at, :ended_at
                )
                ON CONFLICT (session_id) DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    channel = EXCLUDED.channel,
                    call_date = EXCLUDED.call_date,
                    status = EXCLUDED.status,
                    outcome = EXCLUDED.outcome,
                    started_at = EXCLUDED.started_at,
                    ended_at = EXCLUDED.ended_at
                """
            ),
            plan.sessions,
        )
    if plan.episodes:
        connection.execute(
            text(
                """
                INSERT INTO public.episodes (
                    session_id, customer_id, summary_masked, generated_at
                )
                VALUES (
                    :session_id, :customer_id, :summary_masked, :generated_at
                )
                ON CONFLICT (session_id) DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    summary_masked = EXCLUDED.summary_masked,
                    generated_at = EXCLUDED.generated_at
                """
            ),
            plan.episodes,
        )
    if plan.orders:
        connection.execute(
            text(
                """
                INSERT INTO public.orders (
                    order_id, tracking, customer_id, source_session_id, status,
                    total_vnd, order_date
                )
                VALUES (
                    :order_id, :tracking, :customer_id, :source_session_id, :status,
                    :total_vnd, :order_date
                )
                ON CONFLICT (order_id) DO UPDATE SET
                    tracking = EXCLUDED.tracking,
                    customer_id = EXCLUDED.customer_id,
                    source_session_id = EXCLUDED.source_session_id,
                    status = EXCLUDED.status,
                    total_vnd = EXCLUDED.total_vnd,
                    order_date = EXCLUDED.order_date
                """
            ),
            plan.orders,
        )
        connection.execute(
            text("DELETE FROM public.order_items WHERE order_id = :order_id"),
            [{"order_id": row["order_id"]} for row in plan.orders],
        )
    if plan.order_items:
        connection.execute(
            text(
                """
                INSERT INTO public.order_items (
                    order_id, sku, quantity, unit_price_vnd, line_total_vnd, product_snapshot
                )
                VALUES (
                    :order_id, :sku, :quantity, :unit_price_vnd, :line_total_vnd,
                    CAST(:product_snapshot AS jsonb)
                )
                """
            ),
            plan.order_items,
        )
    connection.execute(
        text(
            """
            INSERT INTO public.policies (policy_id, title, visibility)
            VALUES (:policy_id, :title, :visibility)
            ON CONFLICT (policy_id) DO UPDATE SET
                title = EXCLUDED.title,
                visibility = EXCLUDED.visibility
            """
        ),
        plan.policies,
    )
    connection.execute(
        text(
            """
            INSERT INTO public.policy_versions (policy_id, effective_from, effective_to)
            VALUES (:policy_id, :effective_from, :effective_to)
            ON CONFLICT (policy_id, effective_from) DO UPDATE SET
                effective_to = EXCLUDED.effective_to
            """
        ),
        plan.policy_versions,
    )


def sql_literal(value: object) -> str:
    """Literal SQL an toàn cho NULL, bool, số và text."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert_sql(
    table: str,
    columns: list[str],
    rows: list[dict],
    casts: dict[str, str] | None = None,
) -> str:
    """Một lệnh INSERT nhiều dòng. Bỏ qua khi không có dòng."""
    if not rows:
        return ""
    casts = casts or {}
    values: list[str] = []
    for row in rows:
        cells: list[str] = []
        for column in columns:
            literal = sql_literal(row[column])
            if column in casts and literal != "NULL":
                literal = f"{literal}::{casts[column]}"
            cells.append(literal)
        values.append("(" + ", ".join(cells) + ")")
    column_sql = ", ".join(columns)
    return (
        f"INSERT INTO public.{table} ({column_sql})\nVALUES\n"
        + ",\n".join(values)
        + ";\n"
    )


def render_seed_sql(plan: ImportPlan) -> str:
    """SQL để `npx supabase db reset` nạp lại toàn bộ dữ liệu nguồn."""
    statements = [
        insert_sql(
            "customers",
            ["customer_id", "name", "honorific", "status", "phone", "zalo_id", "fb_id", "region"],
            plan.customers,
        ),
        insert_sql(
            "products",
            ["sku", "name", "category", "brand", "list_price_vnd", "attributes", "stock"],
            plan.products,
            {"attributes": "jsonb"},
        ),
        insert_sql(
            "product_variants",
            ["variant_sku", "product_sku", "size", "color", "price_delta_vnd", "stock"],
            plan.variants,
        ),
        insert_sql(
            "promotions",
            [
                "promo_code", "name", "type", "starts_on", "ends_on", "stackable",
                "discount_vnd", "discount_percent", "gift_sku", "min_order_vnd", "conditions",
            ],
            plan.promotions,
            {"conditions": "jsonb"},
        ),
        insert_sql(
            "promotion_products",
            ["promo_code", "target_type", "target_value"],
            plan.promotion_products,
        ),
        insert_sql(
            "inventory_snapshots",
            ["sku", "variant_sku", "observed_on", "quantity"],
            plan.inventory,
        ),
        insert_sql(
            "conversation_sessions",
            [
                "session_id", "customer_id", "channel", "call_date", "status",
                "outcome", "started_at", "ended_at",
            ],
            plan.sessions,
        ),
        insert_sql(
            "episodes",
            ["session_id", "customer_id", "summary_masked", "generated_at"],
            plan.episodes,
        ),
        insert_sql(
            "orders",
            [
                "order_id", "tracking", "customer_id", "source_session_id",
                "status", "total_vnd", "order_date",
            ],
            plan.orders,
        ),
        insert_sql(
            "order_items",
            [
                "order_id", "sku", "quantity", "unit_price_vnd",
                "line_total_vnd", "product_snapshot",
            ],
            plan.order_items,
            {"product_snapshot": "jsonb"},
        ),
        insert_sql(
            "policies",
            ["policy_id", "title", "visibility"],
            plan.policies,
        ),
        insert_sql(
            "policy_versions",
            ["policy_id", "effective_from", "effective_to"],
            plan.policy_versions,
        ),
    ]
    body = "\n".join(statement for statement in statements if statement)
    return (
        "-- Generated by scripts/database/import_reference_data.py --write-seed\n"
        "-- `npx supabase db reset` chạy file này sau migration.\n"
        "-- Sửa data/catalog hoặc data/policy rồi sinh lại, không sửa tay file này.\n"
        "BEGIN;\n\n"
        f"{body}\n"
        "COMMIT;\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nạp catalog và metadata chính sách vào Postgres.")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in số dòng, không ghi database")
    parser.add_argument(
        "--write-seed",
        action="store_true",
        help="Ghi supabase/seed.sql để db reset nạp lại dữ liệu",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Cho phép ghi vào host khác localhost. Mặc định từ chối.",
    )
    args = parser.parse_args(argv)

    plan = build_plan(DATA_DIR)
    print(format_plan(plan))
    if plan.errors:
        print("[IMPORT] Dừng vì dữ liệu nguồn không khớp ràng buộc.")
        return 1
    if args.write_seed:
        seed_path = PROJECT_ROOT / "supabase" / "seed.sql"
        seed_path.write_text(render_seed_sql(plan), encoding="utf-8")
        print(f"[IMPORT] Đã ghi {seed_path}")
    if args.dry_run or args.write_seed:
        if args.dry_run:
            print("[IMPORT] Dry-run. Không ghi database.")
        return 0

    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    database_url = (os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print("[IMPORT] Thiếu SUPABASE_DATABASE_URL.")
        return 1
    print(f"[IMPORT] Target database: {describe_target(database_url)}")
    if not is_local_database(database_url) and not args.allow_remote:
        print("[IMPORT] Host không phải local. Thêm --allow-remote nếu cố ý ghi lên remote.")
        return 1

    engine = create_engine(_engine_url(database_url))
    with engine.begin() as connection:
        apply_plan(connection, plan)
    print("[IMPORT] Đã ghi xong. Mở Studio tại http://127.0.0.1:54323 để xem các bảng public.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
