"""
tests/test_hybrid_retriever.py
Kiểm tra hoạt động của QdrantVectorStore và Hybrid Search (Dense + Sparse) với in-memory client.
"""

from qdrant_client import QdrantClient
from src.services.vector_store import QdrantVectorStore


def test_qdrant_hybrid_search():
    # Tạo store chạy trực tiếp trên RAM để test
    store = QdrantVectorStore()
    store.client = QdrantClient(":memory:")

    collection_name = "test_products"
    store.init_collection(collection_name, dense_dim=4)

    documents = [
        {
            "_id": "SKU-PH-A55",
            "sku": "SKU-PH-A55",
            "name": "Samsung Galaxy A55",
            "category": "dien_thoai",
            "min_price": 9490000,
            "in_stock": True,
            "embedding_text": "Điện thoại Samsung Galaxy A55 pin 5000 mAh"
        },
        {
            "_id": "SKU-LT-MBA",
            "sku": "SKU-LT-MBA",
            "name": "MacBook Air M3",
            "category": "laptop",
            "min_price": 27990000,
            "in_stock": True,
            "embedding_text": "Laptop MacBook Air M3 mỏng nhẹ"
        }
    ]

    embeddings = [
        {
            "dense": [0.1, 0.2, 0.8, 0.1],
            "sparse": {"indices": [101, 202], "values": [0.9, 0.5]}
        },
        {
            "dense": [0.8, 0.1, 0.1, 0.9],
            "sparse": {"indices": [303, 404], "values": [0.7, 0.8]}
        }
    ]

    store.upsert_catalog_documents(collection_name, documents, embeddings)

    # Test get_by_sku
    doc = store.get_by_sku(collection_name, "SKU-PH-A55")
    assert doc is not None
    assert doc["name"] == "Samsung Galaxy A55"

    # Test hybrid search
    results = store.hybrid_search(
        collection_name=collection_name,
        query_dense=[0.1, 0.2, 0.7, 0.1],
        query_sparse={"indices": [101], "values": [0.9]},
        top_k=1,
        category="dien_thoai"
    )

    assert len(results) == 1
    assert results[0]["sku"] == "SKU-PH-A55"
    print("Test Qdrant Hybrid Search (Dense + Sparse) passed successfully!")


if __name__ == "__main__":
    test_qdrant_hybrid_search()

