"""
src/memory/semantic_rag/retriever.py
RAG query wrapper built on the HybridSearchEngine:
- Dense retrieval with Gemini embeddings.
- Sparse retrieval with BM25S.
- Qdrant RRF hybrid search and SKU lookup.
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
        """Search for products with dense, sparse, and RRF hybrid retrieval."""
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
        """Search store policies such as returns, warranty, and delivery."""
        return self.engine.search_policies(query=query, top_k=top_k)

    def get_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """Look up a product in Qdrant by SKU."""
        return self.engine.get_by_sku(sku)
