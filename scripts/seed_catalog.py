"""
scripts/seed_catalog.py
Nạp dữ liệu từ data/catalog/catalog.json, chuẩn hóa và:
1. Đồng bộ dữ liệu có cấu trúc lên MongoDB Atlas (nếu có MONGODB_URI).
2. Sinh Dense (1024 dims) và Sparse (lexical weights) embeddings bằng BGE-M3 (BAAI/bge-m3).
3. Đẩy vào Qdrant Vector DB với Hybrid Index (Dense + Sparse) phục vụ RRF search.

Chạy lệnh:
    python scripts/seed_catalog.py
"""

import os
import sys
import json
from typing import List
from dotenv import load_dotenv

# Tải biến môi trường từ .env
load_dotenv()

# Hỗ trợ UTF-8 cho Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thêm đường dẫn project vào sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.memory.semantic_rag.ingestion import parse_catalog_file


def main():
    catalog_path = os.path.join(BASE_DIR, "data", "catalog", "catalog.json")
    if not os.path.exists(catalog_path):
        print(f"Lỗi: Không tìm thấy file catalog tại {catalog_path}")
        return

    print(f"[1/4] Đang đọc và chuẩn hóa catalog từ: {catalog_path}")
    products_docs, policies_docs = parse_catalog_file(catalog_path)
    print(f"   -> Đã chuẩn hóa {len(products_docs)} sản phẩm và {len(policies_docs)} chính sách.")

    # Lưu bản đã xử lý vào data/processed
    processed_dir = os.path.join(BASE_DIR, "data", "processed")
    os.makedirs(processed_dir, exist_ok=True)

    prod_out = os.path.join(processed_dir, "products_normalized.json")
    pol_out = os.path.join(processed_dir, "policies_normalized.json")

    with open(prod_out, "w", encoding="utf-8") as f:
        json.dump(products_docs, f, ensure_ascii=False, indent=2)

    with open(pol_out, "w", encoding="utf-8") as f:
        json.dump(policies_docs, f, ensure_ascii=False, indent=2)

    print(f"[2/4] Đã lưu file chuẩn hóa tại data/processed/.")

    # 3. Đồng bộ MongoDB Atlas (Document Store)
    mongo_uri = os.getenv("MONGODB_URI")
    if mongo_uri:
        print("[3/4] Đang đồng bộ tài liệu sang MongoDB Atlas...")
        try:
            from pymongo import MongoClient, ReplaceOne
            client = MongoClient(mongo_uri)
            db = client[os.getenv("MONGODB_DB_NAME", "SC2026")]

            prod_ops = [ReplaceOne({"_id": p["_id"]}, p, upsert=True) for p in products_docs]
            pol_ops = [ReplaceOne({"_id": pol["_id"]}, pol, upsert=True) for pol in policies_docs]

            res_prod = db["products"].bulk_write(prod_ops)
            res_pol = db["policies"].bulk_write(pol_ops)

            print(f"   -> MongoDB Atlas: {res_prod.matched_count + len(res_prod.upserted_ids)} products, "
                  f"{res_pol.matched_count + len(res_pol.upserted_ids)} policies.")
        except Exception as e:
            print(f"   [!] Lỗi khi đồng bộ MongoDB: {e}")
    else:
        print("[3/4] Bỏ qua MongoDB (chưa cấu hình MONGODB_URI).")

    # 4. Sinh Embedding BGE-M3 (Dense + Sparse) và đẩy vào Qdrant
    print("[4/4] Đang khởi tạo BGE-M3 và Qdrant Vector Store...")
    try:
        from src.services.bge_m3_service import BGEM3Service
        from src.services.vector_store import QdrantVectorStore

        embedder = BGEM3Service()
        vector_store = QdrantVectorStore()

        # Embedding Products
        print("   -> Đang sinh BGE-M3 embeddings cho 32 sản phẩm (Dense + Sparse)...")
        prod_texts = [p["embedding_text"] for p in products_docs]
        prod_embeddings = embedder.encode_documents(prod_texts)

        vector_store.upsert_catalog_documents("products", products_docs, prod_embeddings)

        # Embedding Policies
        print("   -> Đang sinh BGE-M3 embeddings cho các chính sách...")
        pol_texts = [pol["embedding_text"] for pol in policies_docs]
        pol_embeddings = embedder.encode_documents(pol_texts)

        vector_store.upsert_catalog_documents("policies", policies_docs, pol_embeddings)

        print("\n Hoàn tất nạp BGE-M3 Dense + Sparse embeddings vào Qdrant!")

    except ImportError as ie:
        print(f"   [!] Thiếu thư viện cho Qdrant / BGE-M3: {ie}")
        print("   Cài đặt: pip install qdrant-client FlagEmbedding torch")
    except Exception as e:
        print(f"   [!] Lỗi trong quá trình nạp Qdrant: {e}")


if __name__ == "__main__":
    main()
