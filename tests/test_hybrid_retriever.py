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
        if "samsung" in text.lower() or "a55" in text.lower():
            vec[0] = 0.9
            vec[1] = 0.5
        elif "macbook" in text.lower() or "m3" in text.lower():
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
            "_id": "SKU-PH-A55-128",
            "sku": "SKU-PH-A55-128",
            "name": "Samsung Galaxy A55 5G",
            "category": "dien_thoai",
            "min_price": 9490000,
            "max_price": 10490000,
            "in_stock": True,
            "embedding_text": "Điện thoại Samsung Galaxy A55 5G pin 5000 mAh chip Exynos 1480"
        },
        {
            "_id": "SKU-LT-MBA-M3-256",
            "sku": "SKU-LT-MBA-M3-256",
            "name": "MacBook Air M3",
            "category": "laptop",
            "min_price": 27990000,
            "max_price": 32990000,
            "in_stock": True,
            "embedding_text": "Laptop MacBook Air M3 mỏng nhẹ pin trâu màn hình Retina"
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
        sparse_embedder=sparse_embedder
    )

    # 4. Search with RRF.
    results = search_engine.search_products("Samsung Galaxy A55 pin trâu", top_k=1)

    assert len(results) == 1, "Phải tìm thấy 1 kết quả"
    assert results[0]["sku"] == "SKU-PH-A55-128", "Kết quả tìm kiếm phải là Samsung A55"
    assert "_score" in results[0], "Kết quả phải có điểm RRF fusion"

    # 5. Test get_by_sku.
    doc = search_engine.get_by_sku("SKU-LT-MBA-M3-256")
    assert doc is not None
    assert doc["name"] == "MacBook Air M3"

    print(" Tất cả các test cho kiến trúc Gemini 768 Dense + BM25S Sparse + Qdrant RRF đều ĐẠT!")


if __name__ == "__main__":
    test_gemini_bm25s_hybrid_search()
