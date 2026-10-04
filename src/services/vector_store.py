"""
Qdrant vector database client wrapper for cloud and local deployments.
Supports dense Gemini embeddings, sparse BM25S vectors, RRF fusion, and
metadata filters for category, stock status, and price range.
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

# Fixed namespace used to generate stable UUIDs from SKUs or document IDs.
SKU_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def get_deterministic_uuid(key: str) -> str:
    """Generate a stable UUIDv5 from a SKU for use as a Qdrant point ID."""
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
            # Use local storage when no Qdrant server or explicit path is configured.
            default_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data", "qdrant_storage"
            )
            self.client = QdrantClient(path=default_path)

    def init_collection(
        self,
        collection_name: str,
        dense_dim: Optional[int] = None,
        recreate: bool = False,
    ):
        """Create a collection with dense and sparse vector indexes.

        Dense vectors use Gemini embeddings; sparse vectors use BM25S indices
        and scores.
        """
        dense_dim = dense_dim or int(os.getenv("GEMINI_EMBEDDING_DIMENSION", "768"))
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
            print(f" Đã khởi tạo Qdrant collection '{collection_name}' (Dense 768-dim + Sparse BM25S).")

        if collection_name == "products":
            self._ensure_product_payload_indexes()

    def _ensure_product_payload_indexes(self) -> None:
        """Create the payload indexes required by product query filters."""
        collection_name = "products"
        payload_schema = self.client.get_collection(collection_name).payload_schema
        indexes = (
            ("category", models.PayloadSchemaType.KEYWORD),
            ("in_stock", models.PayloadSchemaType.BOOL),
            ("min_price", models.PayloadSchemaType.INTEGER),
        )

        for field_name, field_schema in indexes:
            if field_name not in payload_schema:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                )


    def upsert_catalog_documents(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        dense_vectors: List[List[float]],
        sparse_vectors: List[Dict[str, Any]]
    ):
        """Store dense and sparse BM25S vectors in the same Qdrant collection."""
        self.init_collection(collection_name)
        points = []

        for doc, dense, sparse in zip(documents, dense_vectors, sparse_vectors):
            doc_id = doc.get("_id") or doc.get("sku")
            point_id = get_deterministic_uuid(str(doc_id))

            vector_dict = {
                "dense": dense,
                "sparse": SparseVector(
                    indices=sparse["indices"],
                    values=sparse["values"]
                )
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector_dict,
                    payload=doc
                )
            )

        self.client.upsert(
            collection_name=collection_name,
            points=points
        )
        print(f" Đã upsert {len(points)} documents (Dense 768 + Sparse BM25S) vào Qdrant '{collection_name}'.")

    def hybrid_search_rrf(
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
        """Run hybrid RRF search in Qdrant with optional metadata filters."""
        if collection_name == "products":
            self._ensure_product_payload_indexes()

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
            price_range = {}
            if min_price is not None:
                price_range["gte"] = min_price
            if max_price is not None:
                price_range["lte"] = max_price
            must_conditions.append(
                FieldCondition(key="min_price", range=Range(**price_range))
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
                    limit=max(top_k * 5, top_k),
                    filter=query_filter,
                ),
                Prefetch(
                    query=sparse_vector,
                    using="sparse",
                    limit=max(top_k * 5, top_k),
                    filter=query_filter,
                )
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            query_filter=query_filter,
        )

        results = []
        for point in response.points:
            item = dict(point.payload)
            item["_score"] = point.score
            results.append(item)
        return results

    def get_by_sku(self, collection_name: str, sku: str) -> Optional[Dict[str, Any]]:
        """Look up a product by SKU."""
        point_id = get_deterministic_uuid(sku)
        records = self.client.retrieve(
            collection_name=collection_name,
            ids=[point_id],
            with_payload=True
        )
        if records:
            return records[0].payload
        return None
