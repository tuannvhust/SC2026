"""Kiểm tra cách importer map catalog và policy, không nối database."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "database" / "import_reference_data.py"


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_reference_data", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


importer = _load_importer()


def test_promotion_target_covers_sku_category_and_all():
    assert importer.promotion_target("SKU-AP-X") == ("sku", "SKU-AP-X")
    assert importer.promotion_target("category:gia-dung") == ("category", "gia-dung")
    assert importer.promotion_target("*") == ("all", "all")


def test_inventory_event_uses_variant_sku_when_the_code_is_a_variant():
    plan = importer.build_plan(ROOT / "data")
    variant_rows = [row for row in plan.inventory if row["variant_sku"] == "SKU-SN-RUN2-41-DEN"]
    product_rows = [row for row in plan.inventory if row["sku"] == "SKU-AP-PRO"]

    assert variant_rows
    assert all(row["sku"] is None for row in variant_rows)
    assert product_rows
    assert all(row["variant_sku"] is None for row in product_rows)
    assert plan.skipped_inventory == []


def test_plan_keeps_business_order_and_session_ids():
    plan = importer.build_plan(ROOT / "data")
    orders = {row["order_id"]: row for row in plan.orders}
    sessions = {row["session_id"]: row for row in plan.sessions}
    episodes = {row["session_id"]: row for row in plan.episodes}

    assert plan.errors == []
    assert len(plan.products) > 0
    assert len(plan.variants) > 0
    assert any(row["promo_code"] == "AIR-OCT" for row in plan.promotions)
    assert ("AIR-OCT", "sku", "SKU-AP-PRO") in {
        (row["promo_code"], row["target_type"], row["target_value"])
        for row in plan.promotion_products
    }
    assert orders["OD188213"]["customer_id"] == "C031"
    assert orders["OD188213"]["source_session_id"] == "S000001"
    assert orders["OD301177"]["tracking"] == "GHN7781234"
    assert orders["OD301177"]["source_session_id"] is None
    assert {row["order_id"] for row in plan.order_items} == {"OD188213", "OD301177"}
    assert all(row["quantity"] == 1 for row in plan.order_items)
    assert sessions["S000001"]["outcome"] == "chot_don"
    assert "Hoàng Cầu" in episodes["S000001"]["summary_masked"]
    assert set(sessions) == {"S000001", "S000002", "S000003"}
    assert len(plan.policies) == 14
    assert any(row["visibility"] == "internal" for row in plan.policies)
    assert any(row["visibility"] == "expired" for row in plan.policies)

    seed_sql = importer.render_seed_sql(plan)
    assert "INSERT INTO public.orders" in seed_sql
    assert "'OD188213'" in seed_sql
    assert "'S000003'" in seed_sql


def test_local_database_guard_accepts_localhost_only():
    assert importer.is_local_database("postgresql://postgres:postgres@127.0.0.1:54322/postgres")
    assert not importer.is_local_database(
        "postgresql://postgres:postgres@db.example.supabase.co:5432/postgres"
    )
