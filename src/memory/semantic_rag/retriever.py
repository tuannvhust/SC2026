"""
src/memory/semantic_rag/retriever.py
Wrapper truy vấn cho RAG, sử dụng HybridSearchEngine từ hybrid_search.py:
- Nhánh 1 (Dense): Gemini text-embedding-004 (768 chiều)
- Nhánh 2 (Sparse): BM25S (CPU local)
- Qdrant RRF Hybrid Search & SKU Lookup
"""

from typing import List, Dict, Any, Optional
from src.memory.semantic_rag.hybrid_search import HybridSearchEngine


class SemanticRetriever:
    def __init__(self, search_engine: Optional[HybridSearchEngine] = None):
        self.engine = search_engine or HybridSearchEngine()

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
        Tìm kiếm sản phẩm Hybrid (Gemini 768 + BM25S + RRF Fusion).
        """
        return self.engine.search_products(
            query=query,
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
        return self.engine.search_policies(query=query, top_k=top_k)

    def get_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Tra cứu trực tiếp sản phẩm bằng mã SKU trong Qdrant.
        """
        return self.engine.get_by_sku(sku)
