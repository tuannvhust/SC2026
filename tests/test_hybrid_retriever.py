"""
tests/test_hybrid_retriever.py
Test the hybrid retrieval architecture:
- Dense 768-dimensional embeddings from Gemini.
- Sparse vectors from bm25s on the local CPU.
- Both vector types stored in one Qdrant collection.
- HybridSearchEngine uses RRF fusion.
"""

import sys
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qdrant_client import QdrantClient
from src.services.vector_store import QdrantVectorStore
from src.services.bm25s_embedder import BM25SparseEmbedder
from src.memory.semantic_rag.hybrid_search import HybridSearchEngine


class MockGeminiEmbedder:
    def __init__(self, dimension=768):
        self.dimension = dimension

    def embed_text(self, text: str):
        # Create a mock 768-dimensional vector with keyword-specific values.
        vec = [0.0] * self.dimension
        if "airpure" in text.lower() or "sku-ap-x" in text.lower():
            vec[0] = 0.9
            vec[1] = 0.5
        elif "runlite" in text.lower() or "sku-sn-run1" in text.lower():
            vec[10] = 0.9
            vec[11] = 0.5
        return vec

    def embed_batch(self, texts):
        return [self.embed_text(t) for t in texts]


def test_gemini_bm25s_hybrid_search():
    # 1. Initialize an in-memory Qdrant instance.
    store = QdrantVectorStore()
    store.client = QdrantClient(":memory:")

    collection_name = "products"
    store.init_collection(collection_name, dense_dim=768)

    # 2. Prepare sample documents.
    documents = [
        {
            "_id": "SKU-AP-X",
            "sku": "SKU-AP-X",
            "name": "Máy lọc không khí AirPure X",
            "category": "gia-dung/may-loc-khong-khi",
            "list_price_vnd": 4_890_000,
            "min_price": 4_890_000,
            "max_price": 4_890_000,
            "stock": 40,
            "total_stock": 40,
            "in_stock": True,
            "embedding_text": "Máy lọc không khí AirPure X bộ lọc HEPA H13"
        },
        {
            "_id": "SKU-SN-RUN1",
            "sku": "SKU-SN-RUN1",
            "name": "Giày chạy bộ RunLite 1",
            "category": "thoi-trang/giay",
            "list_price_vnd": 1_290_000,
            "min_price": 1_290_000,
            "max_price": 1_340_000,
            "stock": 48,
            "total_stock": 48,
            "in_stock": True,
            "variants": [
                {
                    "variant_sku": "SKU-SN-RUN1-42-DEN",
                    "size": 42,
                    "color": "đen",
                    "stock": 4,
                    "price_delta_vnd": 50_000,
                }
            ],
            "embedding_text": "Giày chạy bộ RunLite 1 size 42 màu đen"
        }
    ]

    corpus = [d["embedding_text"] for d in documents]

    # Dense vector branch.
    dense_embedder = MockGeminiEmbedder(dimension=768)
    dense_vectors = dense_embedder.embed_batch(corpus)

    # BM25S sparse vector branch.
    sparse_embedder = BM25SparseEmbedder()
    sparse_vectors = sparse_embedder.fit_corpus(corpus)

    # Store both vector types in the same Qdrant collection.
    store.upsert_catalog_documents(collection_name, documents, dense_vectors, sparse_vectors)

    # 3. Initialize the hybrid search engine.
    search_engine = HybridSearchEngine(
        vector_store=store,
        dense_embedder=dense_embedder,
        sparse_prod_embedder=sparse_embedder,
    )

    # 4. Search with RRF.
    results = search_engine.search_products("AirPure X lọc HEPA", top_k=1)

    assert len(results) == 1, "Phải tìm thấy 1 kết quả"
    assert results[0]["sku"] == "SKU-AP-X"
    assert "_score" in results[0], "Kết quả phải có điểm RRF fusion"

    # 5. Test get_by_sku.
    doc = search_engine.get_by_sku("SKU-SN-RUN1")
    assert doc is not None
    assert doc["name"] == "Giày chạy bộ RunLite 1"
    assert not {
        "list_price_vnd",
        "min_price",
        "max_price",
        "stock",
        "total_stock",
        "in_stock",
    } & doc.keys()
    assert doc["variants"] == [
        {
            "variant_sku": "SKU-SN-RUN1-42-DEN",
            "size": 42,
            "color": "đen",
        }
    ]

    try:
        search_engine.search_products(
            "RunLite",
            in_stock_only=True,
        )
    except ValueError as exc:
        assert "live stock or price data" in str(exc)
    else:
        raise AssertionError("Qdrant must not filter against absent live payload fields.")

    print(" Tất cả các test cho kiến trúc Gemini 768 Dense + BM25S Sparse + Qdrant RRF đều ĐẠT!")


if __name__ == "__main__":
    test_gemini_bm25s_hybrid_search()
