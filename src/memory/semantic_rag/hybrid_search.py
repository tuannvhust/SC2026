"""
src/memory/semantic_rag/hybrid_search.py
Logic tÃ¬m kiáº¿m Hybrid Search tÃ¡ch biá»‡t cho táº§ng Semantic RAG:
1. Xá»­ lÃ½ song song (Parallel Processing):
   - NhÃ¡nh 1 (Dense): Gá»­i query qua Gemini API (text-embedding-004) -> Vector 768 chiá»u.
   - NhÃ¡nh 2 (Sparse): DÃ¹ng bm25s (cháº¡y trÃªn CPU local) -> TrÃ­ch xuáº¥t chá»‰ má»¥c tá»« khÃ³a chÃ­nh xÃ¡c.
2. Truy váº¥n Qdrant:
   - Gá»­i Ä‘á»“ng thá»i cáº£ 2 vector vÃ o Qdrant.
   - Qdrant tá»± Ä‘á»™ng trá»™n káº¿t quáº£ báº±ng thuáº­t toÃ¡n RRF (Reciprocal Rank Fusion) Ä‘á»ƒ tráº£ vá» káº¿t quáº£ tá»‘i Æ°u nháº¥t.
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
        sparse_embedder: Optional[BM25SparseEmbedder] = None  # alias cho cáº£ 2 náº¿u truyá»n 1 embedder
    ):
        self.vector_store = vector_store or QdrantVectorStore()
        self.dense_embedder = dense_embedder or GeminiDenseEmbedder()

        # Náº¡p BM25 sparse index Ä‘Ã£ lÆ°u (hoáº·c dÃ¹ng embedder Ä‘Æ°á»£c truyá»n vÃ o)
        bm25_prod_dir = os.path.join(BASE_DIR, "data", "processed", "bm25_products")
        bm25_pol_dir = os.path.join(BASE_DIR, "data", "processed", "bm25_policies")

        self.sparse_prod_embedder = sparse_prod_embedder or sparse_embedder or BM25SparseEmbedder(index_dir=bm25_prod_dir)
        self.sparse_pol_embedder = sparse_pol_embedder or sparse_embedder or BM25SparseEmbedder(index_dir=bm25_pol_dir)

    def _encode_query_parallel(
        self,
        query: str,
        sparse_embedder: BM25SparseEmbedder
    ) -> tuple[List[float], Dict[str, Any]]:
        """
        Xá»­ lÃ½ song song 2 nhÃ¡nh:
        - NhÃ¡nh 1: Gemini Dense (768 chiá»u)
        - NhÃ¡nh 2: BM25S Sparse
        """
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
        """
        TÃ¬m kiáº¿m sáº£n pháº©m báº±ng Hybrid Search (Dense 768 + Sparse BM25S + RRF Fusion).
        """
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
        """
        TÃ¬m kiáº¿m chÃ­nh sÃ¡ch bÃ¡n hÃ ng (Ä‘á»•i tráº£, báº£o hÃ nh, giao hÃ ng COD) báº±ng RRF Fusion.
        """
        query_dense, query_sparse = self._encode_query_parallel(query, self.sparse_pol_embedder)

        return self.vector_store.hybrid_search_rrf(
            collection_name="policies",
            query_dense=query_dense,
            query_sparse=query_sparse,
            top_k=top_k
        )

    def get_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Tra cá»©u chÃ­nh xÃ¡c sáº£n pháº©m theo mÃ£ SKU tá»« Qdrant.
        """
        return self.vector_store.get_by_sku("products", sku)
