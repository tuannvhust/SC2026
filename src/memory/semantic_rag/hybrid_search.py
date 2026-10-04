"""
src/memory/semantic_rag/hybrid_search.py
Hybrid search logic for the semantic RAG layer:
1. Embed queries concurrently using Gemini dense embeddings and BM25S sparse vectors.
2. Query Qdrant with both vectors and combine results using reciprocal rank fusion (RRF).
"""

import os
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

from src.services.vector_store import QdrantVectorStore
from src.services.gemini_embedder import GeminiDenseEmbedder
from src.services.bm25s_embedder import BM25SparseEmbedder

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class HybridSearchEngine:
    def __init__(
        self,
        vector_store: Optional[QdrantVectorStore] = None,
        dense_embedder: Optional[GeminiDenseEmbedder] = None,
        sparse_prod_embedder: Optional[BM25SparseEmbedder] = None,
        sparse_pol_embedder: Optional[BM25SparseEmbedder] = None,
        sparse_embedder: Optional[BM25SparseEmbedder] = None  # Shared alias for both when one embedder is supplied.
    ):
        self.vector_store = vector_store or QdrantVectorStore()
        self.dense_embedder = dense_embedder or GeminiDenseEmbedder()

        # Load saved BM25 sparse indexes or use the supplied embedders.
        bm25_prod_dir = os.path.join(BASE_DIR, "data", "processed", "bm25_products")
        bm25_pol_dir = os.path.join(BASE_DIR, "data", "processed", "bm25_policies")

        self.sparse_prod_embedder = sparse_prod_embedder or sparse_embedder or BM25SparseEmbedder(index_dir=bm25_prod_dir)
        self.sparse_pol_embedder = sparse_pol_embedder or sparse_embedder or BM25SparseEmbedder(index_dir=bm25_pol_dir)

    def _encode_query_parallel(
        self,
        query: str,
        sparse_embedder: BM25SparseEmbedder
    ) -> tuple[List[float], Dict[str, Any]]:
        """Encode the query concurrently into dense and sparse vectors."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_dense = executor.submit(self.dense_embedder.embed_text, query)
            future_sparse = executor.submit(sparse_embedder.encode_query, query)

            query_dense = future_dense.result()
            query_sparse = future_sparse.result()

        return query_dense, query_sparse

    def search_products(
        self,
        query: str,
        top_k: int = 4,
        category: Optional[str] = None,
        in_stock_only: bool = False,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Search products using dense, sparse, and RRF hybrid retrieval."""
        query_dense, query_sparse = self._encode_query_parallel(query, self.sparse_prod_embedder)

        return self.vector_store.hybrid_search_rrf(
            collection_name="products",
            query_dense=query_dense,
            query_sparse=query_sparse,
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
        """Search store policies using RRF fusion."""
        query_dense, query_sparse = self._encode_query_parallel(query, self.sparse_pol_embedder)

        return self.vector_store.hybrid_search_rrf(
            collection_name="policies",
            query_dense=query_dense,
            query_sparse=query_sparse,
            top_k=top_k
        )

    def get_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """Look up a product in Qdrant by its exact SKU."""
        return self.vector_store.get_by_sku("products", sku)
