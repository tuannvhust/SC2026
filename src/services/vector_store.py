"""
src/services/vector_store.py
Client wrapper cho Qdrant Vector Database, hỗ trợ Hybrid Search kết hợp:
- Dense Vector (BGE-M3 1024 dims, Cosine similarity)
- Sparse Vector (BGE-M3 lexical weights, BM25-like matching)
- Reciprocal Rank Fusion (RRF)
- Metadata Filtering (category, in_stock, min_price, max_price)
"""

import os
import sys
import uuid
from typing import List, Dict, Any, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
from qdrant_client import QdrantClient, models
from qdrant_client.models import (
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    Distance,
    PointStruct,
    SparseVector,
    Prefetch,
    FusionQuery,
    Fusion,
    Filter,
    FieldCondition,
    MatchValue,
    Range
)

# Namespace cố định để tạo UUID ổn định từ SKU / document _id
SKU_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def get_deterministic_uuid(key: str) -> str:
    """Tạo UUIDv5 cố định từ SKU để làm ID trong Qdrant."""
    return str(uuid.uuid5(SKU_NAMESPACE, key))


class QdrantVectorStore:
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        path: Optional[str] = None
    ):
        self.url = url or os.getenv("QDRANT_URL")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.path = path or os.getenv("QDRANT_PATH")

        if self.url:
            self.client = QdrantClient(url=self.url, api_key=self.api_key)
        elif self.path:
            self.client = QdrantClient(path=self.path)
        else:
            # Mặc định lưu cục bộ vào thư mục data/qdrant_storage nếu chưa có Qdrant server
            default_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data", "qdrant_storage"
            )
            self.client = QdrantClient(path=default_path)

    def init_collection(self, collection_name: str, dense_dim: int = 1024, recreate: bool = False):
        """
        Khởi tạo collection với cả 2 chỉ mục: Dense (1024 dims) và Sparse.
        """
        exists = self.client.collection_exists(collection_name)
        if exists and recreate:
            self.client.delete_collection(collection_name)
            exists = False

        if not exists:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(size=dense_dim, distance=Distance.COSINE)
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False)
                    )
                }
            )
            print(f" Đã khởi tạo Qdrant collection '{collection_name}' (Dense + Sparse).")

    def upsert_catalog_documents(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        embeddings: List[Dict[str, Any]]
    ):
        """
        Đẩy danh sách documents kèm vector BGE-M3 (dense + sparse) vào Qdrant.
        """
        self.init_collection(collection_name)
        points = []

        for doc, emb in zip(documents, embeddings):
            doc_id = doc.get("_id") or doc.get("sku")
            point_id = get_deterministic_uuid(str(doc_id))

            sparse_data = emb["sparse"]
            vector_dict = {
                "dense": emb["dense"],
                "sparse": SparseVector(
                    indices=sparse_data["indices"],
                    values=sparse_data["values"]
                )
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector_dict,
                    payload=doc
                )
            )

        # Batch upsert
        self.client.upsert(
            collection_name=collection_name,
            points=points
        )
        print(f" Đã upsert {len(points)} documents vào collection '{collection_name}'.")

    def hybrid_search(
        self,
        collection_name: str,
        query_dense: List[float],
        query_sparse: Dict[str, Any],
        top_k: int = 4,
        category: Optional[str] = None,
        in_stock_only: bool = False,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm Hybrid (Dense + Sparse) với thuật toán Reciprocal Rank Fusion (RRF),
        kết hợp metadata pre-filtering.
        """
        # Xây dựng Filter điều kiện
        must_conditions = []
        if category:
            must_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )
        if in_stock_only:
            must_conditions.append(
                FieldCondition(key="in_stock", match=MatchValue(value=True))
            )
        if min_price is not None or max_price is not None:
            range_cond = {}
            if min_price is not None:
                range_cond["gte"] = min_price
            if max_price is not None:
                range_cond["lte"] = max_price
            must_conditions.append(
                FieldCondition(key="min_price", range=Range(**range_cond))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        sparse_vector = SparseVector(
            indices=query_sparse["indices"],
            values=query_sparse["values"]
        )

        response = self.client.query_points(
            collection_name=collection_name,
            prefetch=[
                Prefetch(
                    query=query_dense,
                    using="dense",
                    limit=top_k * 2,
                    filter=query_filter
                ),
                Prefetch(
                    query=sparse_vector,
                    using="sparse",
                    limit=top_k * 2,
                    filter=query_filter
                )
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            query_filter=query_filter
        )

        results = []
        for point in response.points:
            item = dict(point.payload)
            item["_score"] = point.score
            results.append(item)
        return results

    def get_by_sku(self, collection_name: str, sku: str) -> Optional[Dict[str, Any]]:
        """Tra cứu sản phẩm theo SKU."""
        point_id = get_deterministic_uuid(sku)
        records = self.client.retrieve(
            collection_name=collection_name,
            ids=[point_id],
            with_payload=True
        )
        if records:
            return records[0].payload
        return None
