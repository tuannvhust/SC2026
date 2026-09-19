"""
scripts/seed_mongo.py
Äá»c catalog.json vÃ  náº¡p 1 láº§n vÃ o MongoDB Atlas (Bootstrap ban Ä‘áº§u).
Cháº¡y lá»‡nh:
    python scripts/seed_mongo.py
"""

import os
import sys
import json
from dotenv import load_dotenv

# Há»— trá»£ UTF-8 cho Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.services.mongo_store import MongoStore


def main():
    catalog_path = os.path.join(BASE_DIR, "data", "catalog", "catalog.json")
    if not os.path.exists(catalog_path):
        print(f"Lá»—i: KhÃ´ng tÃ¬m tháº¥y file {catalog_path}")
        return

    print(f"[1/3] Äang Ä‘á»c file catalog tá»«: {catalog_path}")
    with open(catalog_path, "r", encoding="utf-8-sig") as f:
        catalog_data = json.load(f)

    raw_products = catalog_data.get("products", [])
    raw_policies = catalog_data.get("policies", {})

    print(f"   -> TÃ¬m tháº¥y {len(raw_products)} sáº£n pháº©m vÃ  cÃ¡c chÃ­nh sÃ¡ch cá»­a hÃ ng.")

    # Chuáº©n bá»‹ danh sÃ¡ch documents sáº£n pháº©m
    products_docs = []
    cat_names = {
        "dien_thoai": "Äiá»‡n thoáº¡i",
        "laptop": "Laptop",
        "phu_kien_dien_tu": "Phá»¥ kiá»‡n Ä‘iá»‡n tá»­"
    }

    for p in raw_products:
        doc = dict(p)
        sku = p.get("sku")
        doc["_id"] = sku
        doc["sku"] = sku
        doc["category_name"] = cat_names.get(p.get("category"), p.get("category"))
        products_docs.append(doc)

    # Chuáº©n bá»‹ danh sÃ¡ch documents chÃ­nh sÃ¡ch
    policies_docs = [
        {
            "_id": "policy_return",
            "policy_id": "return_policy",
            "title": "ChÃ­nh sÃ¡ch Ä‘á»•i tráº£ sáº£n pháº©m",
            "category": "doi_tra",
            "details": raw_policies.get("return_policy", {})
        },
        {
            "_id": "policy_shipping",
            "policy_id": "shipping_policy",
            "title": "ChÃ­nh sÃ¡ch giao hÃ ng vÃ  thanh toÃ¡n COD",
            "category": "giao_hang",
            "details": raw_policies.get("shipping_policy", {})
        },
        {
            "_id": "policy_warranty",
            "policy_id": "warranty_policy",
            "title": "ChÃ­nh sÃ¡ch báº£o hÃ nh sáº£n pháº©m",
            "category": "bao_hanh",
            "details": raw_policies.get("warranty_policy", {})
        }
    ]

    print("[2/3] Äang káº¿t ná»‘i tá»›i MongoDB Atlas...")
    try:
        mongo_store = MongoStore()
        print(f"   -> Database: '{mongo_store.db_name}'")

        print("[3/3] Äang bootstrap dá»¯ liá»‡u vÃ o MongoDB...")
        count_prod = mongo_store.insert_products_bulk(products_docs)
        count_pol = mongo_store.insert_policies_bulk(policies_docs)

        print(f"   -> Collection 'products': ÄÃ£ náº¡p {count_prod} documents.")
        print(f"   -> Collection 'policies': ÄÃ£ náº¡p {count_pol} documents.")
        print("\n HoÃ n táº¥t náº¡p dá»¯ liá»‡u gá»‘c vÃ o MongoDB Atlas (Bootstrap thÃ nh cÃ´ng)!")

    except Exception as e:
        print(f"[!] Lá»—i khi náº¡p dá»¯ liá»‡u vÃ o MongoDB: {e}")


if __name__ == "__main__":
    main()
