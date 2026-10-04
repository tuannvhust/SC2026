"""
scripts/seed_catalog.py
Load and normalize data from data/catalog/catalog.json, then process it concurrently:
- Dense vectors: send text to the Gemini API and receive 768-dimensional vectors.
- Sparse vectors: use bm25s on the local CPU to extract lexical weights.
- Storage: save both vector types in the same Qdrant collection.
- Document store: sync to MongoDB Atlas when MONGODB_URI is configured.

Run:
    python scripts/seed_catalog.py
"""

import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env.
load_dotenv()

# Enable UTF-8 output in the Windows console.
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add the project root to sys.path.
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
    """Embed the corpus concurrently using Gemini dense and BM25S sparse vectors."""
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

    # Save normalized files under data/processed.
    processed_dir = os.path.join(BASE_DIR, "data", "processed")
    os.makedirs(processed_dir, exist_ok=True)

    prod_out = os.path.join(processed_dir, "products_normalized.json")
    pol_out = os.path.join(processed_dir, "policies_normalized.json")

    with open(prod_out, "w", encoding="utf-8") as f:
        json.dump(products_docs, f, ensure_ascii=False, indent=2)

    with open(pol_out, "w", encoding="utf-8") as f:
        json.dump(policies_docs, f, ensure_ascii=False, indent=2)

    print(f"[2/4] Đã lưu file chuẩn hóa tại data/processed/.")

    # 3. Sync documents to MongoDB Atlas.
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

    # 4. Generate Gemini and BM25S vectors concurrently and upsert them to Qdrant.
    print("[4/4] Bắt đầu xử lý song song và nạp vào Qdrant (Dense 768 + Sparse BM25S)...")
    try:
        dense_embedder = GeminiDenseEmbedder()
        sparse_embedder_prod = BM25SparseEmbedder()
        sparse_embedder_pol = BM25SparseEmbedder()
        vector_store = QdrantVectorStore()

        bm25_prod_dir = os.path.join(processed_dir, "bm25_products")
        bm25_pol_dir = os.path.join(processed_dir, "bm25_policies")

        # Process products.
        print(f"\n--- Xử lý 32 sản phẩm ---")
        prod_texts = [p["embedding_text"] for p in products_docs]
        prod_dense, prod_sparse = parallel_embed_corpus(
            prod_texts, dense_embedder, sparse_embedder_prod, bm25_prod_dir
        )

        vector_store.upsert_catalog_documents("products", products_docs, prod_dense, prod_sparse)

        # Process policies.
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
