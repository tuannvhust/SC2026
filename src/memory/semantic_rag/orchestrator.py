'''src/memory/semantic_rag/orchestrator.py
High‑level entry point for processing a raw user query.
It ties together the router, optional rewriter, hybrid search, reranker and generator.
'''
from threading import Lock
from typing import Any, Dict, List, Optional, Protocol, Tuple

from .query_router import route
from .query_rewriter import rewrite

class _SearchEngine(Protocol):
    def search_products(
        self,
        query: str,
        top_k: int,
        category: Optional[str],
        in_stock_only: bool,
        min_price: Optional[int],
        max_price: Optional[int],
    ) -> List[Dict[str, Any]]:
        ...

    def search_policies(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        ...


class _Reranker(Protocol):
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int,
    ) -> List[Dict[str, Any]]:
        ...


class _Generator(Protocol):
    def generate(self, query: str, context_docs: List[Dict[str, Any]]) -> str:
        ...


_components: Optional[Tuple[_SearchEngine, _Reranker, _Generator]] = None
_components_lock = Lock()


def _get_components() -> Tuple[_SearchEngine, _Reranker, _Generator]:
    """Create the search, reranking and generation components on first search."""
    global _components
    if _components is None:
        with _components_lock:
            if _components is None:
                from .generator import RAGGenerator
                from .hybrid_search import HybridSearchEngine
                from .reranker import Reranker

                _components = (
                    HybridSearchEngine(),
                    Reranker(),
                    RAGGenerator(),
                )
    return _components

def process_raw_query(raw_query: str) -> str:
    """Process a raw user query and return a generated answer.

    Steps:
        1. Route the query → intent, collection, metadata, early response.
        2. If an early response is provided, return it directly.
        3. Optionally rewrite the query (currently identity).
        4. Perform hybrid search on the appropriate collection.
        5. Rerank the retrieved documents.
        6. Generate the final answer using the generator.
    """
    route_res = route(raw_query)
    if route_res.get("early_response"):
        return route_res["early_response"]

    intent = route_res.get("intent")
    collection = route_res.get("collection")
    metadata = route_res.get("metadata", {})
    hybrid_engine, reranker, generator = _get_components()

    rewritten_query = rewrite(raw_query, intent)

    if collection == "products":
        docs = hybrid_engine.search_products(
            rewritten_query,
            top_k=5,
            category=metadata.get("category"),
            in_stock_only=metadata.get("in_stock_only", False),
            min_price=metadata.get("min_price"),
            max_price=metadata.get("max_price"),
        )
    elif collection == "policies":
        docs = hybrid_engine.search_policies(rewritten_query, top_k=5)
    else:
        docs = []

    reranked_docs = reranker.rerank(rewritten_query, docs, top_n=5)
    return generator.generate(rewritten_query, reranked_docs)
