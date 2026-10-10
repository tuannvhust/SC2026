"""
scripts/seed_catalog.py
Nạp dữ liệu từ data/catalog/catalog.json, chuẩn hóa và xử lý song song (Parallel Processing):
- Nhánh 1 (Dense Vector): Gửi văn bản qua Gemini API (text-embedding-004) -> Vector 768 chiều.
- Nhánh 2 (Sparse Vector): Dùng bm25s (chạy trên CPU local) -> Trích xuất chỉ mục từ khóa chính xác.
- Lưu trữ (Qdrant): Lưu cả 2 loại Vector vào cùng 1 Collection trên Qdrant.
- Đồng bộ Document Store sang MongoDB Atlas (nếu có MONGODB_URI).

Chạy lệnh:
    python scripts/seed_catalog.py
"""

import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
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
from src.services.gemini_embedder import GeminiDenseEmbedder
from src.services.bm25s_embedder import BM25SparseEmbedder
from src.services.vector_store import QdrantVectorStore


def parallel_embed_corpus(
    texts: List[str],
    dense_embedder: GeminiDenseEmbedder,
    sparse_embedder: BM25SparseEmbedder,
    save_dir: str
) -> tuple[List[List[float]], List[Dict[str, Any]]]:
    """
    Xử lý song song 2 nhánh:
    - Nhánh 1: Gemini API Dense (768 chiều)
    - Nhánh 2: BM25S Sparse (CPU local)
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        print("   -> [Nhánh 1] Đang gửi qua Gemini API (text-embedding-004: 768 dims)...")
        future_dense = executor.submit(dense_embedder.embed_batch, texts)

        print(f"   -> [Nhánh 2] Đang tính toán Sparse Vector bằng bm25s và lưu vào {save_dir}...")
        future_sparse = executor.submit(sparse_embedder.fit_corpus, texts, save_dir)

        dense_vectors = future_dense.result()
        sparse_vectors = future_sparse.result()

    return dense_vectors, sparse_vectors


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
            print(f"   [!] Ghi chú MongoDB: {e}")
    else:
        print("[3/4] Bỏ qua MongoDB (chưa cấu hình MONGODB_URI).")

    # 4. Xử lý song song (Gemini 768 + bm25s) và nạp vào Qdrant
    print("[4/4] Bắt đầu xử lý song song và nạp vào Qdrant (Dense 768 + Sparse BM25S)...")
    try:
        dense_embedder = GeminiDenseEmbedder()
        sparse_embedder_prod = BM25SparseEmbedder()
        sparse_embedder_pol = BM25SparseEmbedder()
        vector_store = QdrantVectorStore()

        bm25_prod_dir = os.path.join(processed_dir, "bm25_products")
        bm25_pol_dir = os.path.join(processed_dir, "bm25_policies")

        # Xử lý Products
        print(f"\n--- Xử lý 32 sản phẩm ---")
        prod_texts = [p["embedding_text"] for p in products_docs]
        prod_dense, prod_sparse = parallel_embed_corpus(
            prod_texts, dense_embedder, sparse_embedder_prod, bm25_prod_dir
        )

        vector_store.upsert_catalog_documents("products", products_docs, prod_dense, prod_sparse)

        # Xử lý Policies
        print(f"\n--- Xử lý các chính sách ---")
        pol_texts = [pol["embedding_text"] for pol in policies_docs]
        pol_dense, pol_sparse = parallel_embed_corpus(
            pol_texts, dense_embedder, sparse_embedder_pol, bm25_pol_dir
        )

        vector_store.upsert_catalog_documents("policies", policies_docs, pol_dense, pol_sparse)

        print("\n Hoàn tất nạp dữ liệu vào Qdrant (Dense 768 + Sparse BM25S) thành công!")

    except Exception as e:
        print(f"   [!] Lỗi trong quá trình xử lý Qdrant: {e}")


if __name__ == "__main__":
    main()
