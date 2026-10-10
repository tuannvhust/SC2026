"""
scripts/sync_to_qdrant.py
Äá»c dá»¯ liá»‡u tá»« MongoDB Atlas -> Chuáº©n hÃ³a qua ingestion.py -> Embed song song (Gemini 768 + BM25S) -> Upsert Qdrant.
Cháº¡y láº¡i script nÃ y má»—i khi MongoDB cÃ³ thay Ä‘á»•i.

Cháº¡y lá»‡nh:
    python scripts/sync_to_qdrant.py
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
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
    """
    Xá»­ lÃ½ song song 2 nhÃ¡nh:
    - NhÃ¡nh 1: Gemini API Dense (768 chiá»u)
    - NhÃ¡nh 2: BM25S Sparse (CPU local)
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        print("   -> [NhÃ¡nh 1] Äang gá»­i qua Gemini API (text-embedding-004: 768 dims)...")
        future_dense = executor.submit(dense_embedder.embed_batch, texts)

        print(f"   -> [NhÃ¡nh 2] Äang tÃ­nh toÃ¡n Sparse Vector báº±ng bm25s (CPU local)...")
        future_sparse = executor.submit(sparse_embedder.fit_corpus, texts, save_dir)

        dense_vectors = future_dense.result()
        sparse_vectors = future_sparse.result()

    return dense_vectors, sparse_vectors


def main():
    print("[1/4] Äang Ä‘á»c dá»¯ liá»‡u tá»« MongoDB Atlas...")
    try:
        mongo_store = MongoStore()
        raw_products = mongo_store.list_products()
        raw_policies = mongo_store.list_policies()
        print(f"   -> Äá»c thÃ nh cÃ´ng {len(raw_products)} products vÃ  {len(raw_policies)} policies tá»« Mongo.")
    except Exception as e:
        print(f"[!] Lá»—i khi Ä‘á»c dá»¯ liá»‡u tá»« MongoDB: {e}")
        return

    if not raw_products and not raw_policies:
        print("Cáº£nh bÃ¡o: KhÃ´ng cÃ³ dá»¯ liá»‡u trong MongoDB. Vui lÃ²ng cháº¡y `python scripts/seed_mongo.py` trÆ°á»›c.")
        return

    print("\n[2/4] Chuáº©n hÃ³a tá»«ng document qua ingestion.py...")
    prepared_products = [ingest_product_document(doc) for doc in raw_products]
    prepared_policies = [ingest_policy_document(doc) for doc in raw_policies]
    print(f"   -> ÄÃ£ chuáº©n hÃ³a {len(prepared_products)} sáº£n pháº©m vÃ  {len(prepared_policies)} chÃ­nh sÃ¡ch.")

    print("\n[3/4] Khá»Ÿi táº¡o Qdrant Vector Store vÃ  cÃ¡c Embedders...")
    vector_store = QdrantVectorStore()
    dense_embedder = GeminiDenseEmbedder()
    sparse_embedder_prod = BM25SparseEmbedder()
    sparse_embedder_pol = BM25SparseEmbedder()

    processed_dir = os.path.join(BASE_DIR, "data", "processed")
    bm25_prod_dir = os.path.join(processed_dir, "bm25_products")
    bm25_pol_dir = os.path.join(processed_dir, "bm25_policies")

    print("\n[4/4] Xá»­ lÃ½ song song (Gemini 768 + BM25S) vÃ  Ä‘á»“ng bá»™ lÃªn Qdrant...")

    # Äá»“ng bá»™ Products vÃ o Qdrant
    if prepared_products:
        print("\n--- Äá»“ng bá»™ Collection 'products' ---")
        prod_texts = [p["embedding_text"] for p in prepared_products]
        prod_dense, prod_sparse = parallel_embed_corpus(
            prod_texts, dense_embedder, sparse_embedder_prod, bm25_prod_dir
        )
        vector_store.upsert_catalog_documents("products", prepared_products, prod_dense, prod_sparse)

    # Äá»“ng bá»™ Policies vÃ o Qdrant
    if prepared_policies:
        print("\n--- Äá»“ng bá»™ Collection 'policies' ---")
        pol_texts = [pol["embedding_text"] for pol in prepared_policies]
        pol_dense, pol_sparse = parallel_embed_corpus(
            pol_texts, dense_embedder, sparse_embedder_pol, bm25_pol_dir
        )
        vector_store.upsert_catalog_documents("policies", prepared_policies, pol_dense, pol_sparse)

    print("\n HoÃ n táº¥t Ä‘á»“ng bá»™ dá»¯ liá»‡u tá»« MongoDB sang Qdrant Cloud/Local thÃ nh cÃ´ng!")


if __name__ == "__main__":
    main()
