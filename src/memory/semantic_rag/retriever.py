"""
src/memory/semantic_rag/retriever.py
Truy vấn sản phẩm và chính sách từ Qdrant Vector Store sử dụng:
- BGE-M3 Dense + Sparse embedding
- Reciprocal Rank Fusion (RRF) Hybrid Search
- Tra cứu chính xác theo SKU (get_by_sku)
"""

from typing import List, Dict, Any, Optional
from src.services.vector_store import QdrantVectorStore
from src.services.bge_m3_service import BGEM3Service


class SemanticRetriever:
    def __init__(
        self,
        vector_store: Optional[QdrantVectorStore] = None,
        embedder: Optional[BGEM3Service] = None
    ):
        self.vector_store = vector_store or QdrantVectorStore()
        self.embedder = embedder or BGEM3Service()

    def search_products(
        self,
        query: str,
        top_k: int = 3,
        category: Optional[str] = None,
        in_stock_only: bool = False,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm sản phẩm Hybrid (Dense + Sparse RRF) kết hợp bộ lọc metadata.
        """
        query_emb = self.embedder.encode_query(query)
        return self.vector_store.hybrid_search(
            collection_name="products",
            query_dense=query_emb["dense"],
            query_sparse=query_emb["sparse"],
            top_k=top_k,
            category=category,
            in_stock_only=in_stock_only,
            min_price=min_price,
            max_price=max_price
        )

    def search_policies(
        self,
        query: str,
        top_k: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm chính sách cửa hàng (đổi trả, bảo hành, giao hàng).
        """
        query_emb = self.embedder.encode_query(query)
        return self.vector_store.hybrid_search(
            collection_name="policies",
            query_dense=query_emb["dense"],
            query_sparse=query_emb["sparse"],
            top_k=top_k
        )

    def get_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Tra cứu trực tiếp sản phẩm bằng mã SKU trong Qdrant.
        """
        return self.vector_store.get_by_sku("products", sku)
