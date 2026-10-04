"""
scripts/seed_mongo.py
Load catalog.json and seed MongoDB Atlas with the initial data.
Run:
    python scripts/seed_mongo.py
"""

import os
import sys
import json
from dotenv import load_dotenv

# Enable UTF-8 output in the Windows console.
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
        print(f"Lỗi: Không tìm thấy file {catalog_path}")
        return

    print(f"[1/3] Đang đọc file catalog từ: {catalog_path}")
    with open(catalog_path, "r", encoding="utf-8-sig") as f:
        catalog_data = json.load(f)

    raw_products = catalog_data.get("products", [])
    raw_policies = catalog_data.get("policies", {})

    print(f"   -> Tìm thấy {len(raw_products)} sản phẩm và các chính sách cửa hàng.")

    # Prepare product documents.
    products_docs = []
    cat_names = {
        "dien_thoai": "Điện thoại",
        "laptop": "Laptop",
        "phu_kien_dien_tu": "Phụ kiện điện tử"
    }

    for p in raw_products:
        doc = dict(p)
        sku = p.get("sku")
        doc["_id"] = sku
        doc["sku"] = sku
        doc["category_name"] = cat_names.get(p.get("category"), p.get("category"))
        products_docs.append(doc)

    # Prepare policy documents.
    policies_docs = [
        {
            "_id": "policy_return",
            "policy_id": "return_policy",
            "title": "Chính sách đổi trả sản phẩm",
            "category": "doi_tra",
            "details": raw_policies.get("return_policy", {})
        },
        {
            "_id": "policy_shipping",
            "policy_id": "shipping_policy",
            "title": "Chính sách giao hàng và thanh toán COD",
            "category": "giao_hang",
            "details": raw_policies.get("shipping_policy", {})
        },
        {
            "_id": "policy_warranty",
            "policy_id": "warranty_policy",
            "title": "Chính sách bảo hành sản phẩm",
            "category": "bao_hanh",
            "details": raw_policies.get("warranty_policy", {})
        }
    ]

    print("[2/3] Đang kết nối tới MongoDB Atlas...")
    try:
        mongo_store = MongoStore()
        print(f"   -> Database: '{mongo_store.db_name}'")

        print("[3/3] Đang bootstrap dữ liệu vào MongoDB...")
        count_prod = mongo_store.insert_products_bulk(products_docs)
        count_pol = mongo_store.insert_policies_bulk(policies_docs)

        print(f"   -> Collection 'products': Đã nạp {count_prod} documents.")
        print(f"   -> Collection 'policies': Đã nạp {count_pol} documents.")
        print("\n Hoàn tất nạp dữ liệu gốc vào MongoDB Atlas (Bootstrap thành công)!")

    except Exception as e:
        print(f"[!] Lỗi khi nạp dữ liệu vào MongoDB: {e}")


if __name__ == "__main__":
    main()
