"""
scripts/sync_to_qdrant.py
Read data from MongoDB Atlas, normalize it with ingestion.py, generate Gemini
and BM25S embeddings concurrently, then upsert the results to Qdrant.
Run this script whenever the MongoDB data changes.

Run:
    python scripts/sync_to_qdrant.py
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
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
from src.services.vector_store import QdrantVectorStore
from src.services.gemini_embedder import GeminiDenseEmbedder
from src.services.bm25s_embedder import BM25SparseEmbedder
from src.memory.semantic_rag.ingestion import ingest_product_document, ingest_policy_document


def parallel_embed_corpus(
    texts: List[str],
    dense_embedder: GeminiDenseEmbedder,
    sparse_embedder: BM25SparseEmbedder,
    save_dir: str
) -> tuple[List[List[float]], List[Dict[str, Any]]]:
    """Embed the corpus concurrently using Gemini dense and BM25S sparse vectors."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        print("   -> [Branch 1] Sending texts to the Gemini API (768 dimensions)...")
        future_dense = executor.submit(dense_embedder.embed_batch, texts)

        print(f"   -> [Branch 2] Computing sparse vectors with bm25s on the local CPU...")
        future_sparse = executor.submit(sparse_embedder.fit_corpus, texts, save_dir)

        dense_vectors = future_dense.result()
        sparse_vectors = future_sparse.result()

    return dense_vectors, sparse_vectors


def main():
    print("[1/4] Đang đọc dữ liệu từ MongoDB Atlas...")
    try:
        mongo_store = MongoStore()
        raw_products = mongo_store.list_products()
        raw_policies = mongo_store.list_policies()
        print(f"   -> Đọc thành công {len(raw_products)} products và {len(raw_policies)} policies từ Mongo.")
    except Exception as e:
        print(f"[!] Lỗi khi đọc dữ liệu từ MongoDB: {e}")
        return

    if not raw_products and not raw_policies:
        print("Cảnh báo: Không có dữ liệu trong MongoDB. Vui lòng chạy `python scripts/seed_mongo.py` trước.")
        return

    print("\n[2/4] Chuẩn hóa từng document qua ingestion.py...")
    prepared_products = [ingest_product_document(doc) for doc in raw_products]
    prepared_policies = [ingest_policy_document(doc) for doc in raw_policies]
    print(f"   -> Đã chuẩn hóa {len(prepared_products)} sản phẩm và {len(prepared_policies)} chính sách.")

    print("\n[3/4] Khởi tạo Qdrant Vector Store và các embedders...")
    vector_store = QdrantVectorStore()
    dense_embedder = GeminiDenseEmbedder()
    sparse_embedder_prod = BM25SparseEmbedder()
    sparse_embedder_pol = BM25SparseEmbedder()

    processed_dir = os.path.join(BASE_DIR, "data", "processed")
    bm25_prod_dir = os.path.join(processed_dir, "bm25_products")
    bm25_pol_dir = os.path.join(processed_dir, "bm25_policies")

    print("\n[4/4] Xử lý song song (Gemini 768 + BM25S) và đồng bộ lên Qdrant...")

    # Sync products to Qdrant.
    if prepared_products:
        print("\n--- Đồng bộ collection 'products' ---")
        prod_texts = [p["embedding_text"] for p in prepared_products]
        prod_dense, prod_sparse = parallel_embed_corpus(
            prod_texts, dense_embedder, sparse_embedder_prod, bm25_prod_dir
        )
        vector_store.upsert_catalog_documents("products", prepared_products, prod_dense, prod_sparse)

    # Sync policies to Qdrant.
    if prepared_policies:
        print("\n--- Đồng bộ collection 'policies' ---")
        pol_texts = [pol["embedding_text"] for pol in prepared_policies]
        pol_dense, pol_sparse = parallel_embed_corpus(
            pol_texts, dense_embedder, sparse_embedder_pol, bm25_pol_dir
        )
        vector_store.upsert_catalog_documents("policies", prepared_policies, pol_dense, pol_sparse)

    print("\n Hoàn tất đồng bộ dữ liệu từ MongoDB sang Qdrant Cloud/Local thành công!")


if __name__ == "__main__":
    main()
