'''src/memory/semantic_rag/orchestrator.py
High‑level entry point for processing a raw user query.
It ties together the router, optional rewriter, hybrid search, reranker and generator.
'''
from threading import Lock
from typing import Any, Dict, Iterator, List, Optional, Protocol, Tuple

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
    def warmup(self) -> None:
        ...

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
_reranker: Optional[_Reranker] = None
_components_lock = Lock()


def _get_components() -> Tuple[_SearchEngine, _Reranker, _Generator]:
    """Create the search, reranking and generation components on first search."""
    global _components, _reranker
    if _components is None:
        with _components_lock:
            if _components is None:
                from .generator import RAGGenerator
                from .hybrid_search import HybridSearchEngine
                from .reranker import Reranker

                if _reranker is None:
                    _reranker = Reranker()
                _components = (
                    HybridSearchEngine(),
                    _reranker,
                    RAGGenerator(),
                )
    return _components


def warmup_reranker() -> None:
    """Load and warm the shared reranker before the API starts serving requests."""
    global _reranker
    with _components_lock:
        if _reranker is None:
            from .reranker import Reranker

            _reranker = Reranker()
        _reranker.warmup()


def clear_components() -> None:
    """Release cached pipeline components before shared clients are closed."""
    global _components, _reranker
    with _components_lock:
        _components = None
        _reranker = None


def _retrieve_documents(
    search_engine: _SearchEngine,
    rewritten_query: str,
    route_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    collection = route_result.get("collection")
    metadata = route_result.get("metadata") or {}
    if collection == "products":
        has_constraints = any(
            (
                metadata.get("in_stock_only", False),
                metadata.get("min_price") is not None,
                metadata.get("max_price") is not None,
                metadata.get("room_area_m2") is not None,
            )
        )
        documents = search_engine.search_products(
            rewritten_query,
            top_k=30 if has_constraints else 5,
            category=metadata.get("category"),
        )

        room_area = metadata.get("room_area_m2")
        if room_area is not None:
            documents = [
                document
                for document in documents
                if _supports_room_area(document, float(room_area))
            ]

        from src.tools.tool_repository import filter_catalog_candidates

        return filter_catalog_candidates(
            documents,
            min_price_vnd=metadata.get("min_price"),
            max_price_vnd=metadata.get("max_price"),
            in_stock_only=metadata.get("in_stock_only", False),
        )

    if collection == "policies":
        return search_engine.search_policies(rewritten_query, top_k=5)
    return []


def _supports_room_area(document: Dict[str, Any], requested_area: float) -> bool:
    attributes = document.get("attributes")
    if not isinstance(attributes, dict):
        return False
    supported_area = attributes.get(
        "room_area_m2",
        attributes.get("coverage_m2"),
    )
    if supported_area is None:
        return False
    try:
        return float(supported_area) >= requested_area
    except (TypeError, ValueError):
        return False


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
    hybrid_engine, reranker, generator = _get_components()

    rewritten_query = rewrite(raw_query, intent)
    docs = _retrieve_documents(hybrid_engine, rewritten_query, route_res)

    reranked_docs = reranker.rerank(rewritten_query, docs, top_n=5)
    return generator.generate(rewritten_query, reranked_docs)


def process_raw_query_stream(raw_query: str) -> Iterator[str]:
    """Process a query normally, then stream the generated answer."""
    route_res = route(raw_query)
    if route_res.get("early_response"):
        yield route_res["early_response"]
        return

    intent = route_res.get("intent")
    hybrid_engine, reranker, generator = _get_components()
    rewritten_query = rewrite(raw_query, intent)
    docs = _retrieve_documents(hybrid_engine, rewritten_query, route_res)

    reranked_docs = reranker.rerank(rewritten_query, docs, top_n=5)
    generate_stream = getattr(generator, "generate_stream", None)
    if generate_stream:
        yield from generate_stream(rewritten_query, reranked_docs)
    else:
        yield generator.generate(rewritten_query, reranked_docs)
