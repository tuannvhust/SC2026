"""End-to-end local test for the semantic RAG orchestration pipeline."""

from dataclasses import dataclass, field
from typing import Any

from src.memory.semantic_rag import orchestrator


@dataclass
class FakeSearchEngine:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def search_products(
        self,
        query: str,
        top_k: int,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "category": category,
            }
        )
        return [
            {
                "sku": "SKU-AP-X",
                "name": "Máy lọc không khí AirPure X",
                "category": "gia-dung/may-loc-khong-khi",
                "attributes": {"room_area_m2": 25},
                "embedding_text": "Máy lọc không khí AirPure X",
            }
        ]

    def search_policies(self, query: str, top_k: int) -> list[dict[str, Any]]:
        raise AssertionError("The product pipeline should not search policies.")


@dataclass
class FakeReranker:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def rerank(self, query: str, documents: list[dict[str, Any]], top_n: int):
        self.calls.append({"query": query, "documents": documents, "top_n": top_n})
        return documents[:top_n]


@dataclass
class FakeGenerator:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate(self, query: str, context_docs: list[dict[str, Any]]) -> str:
        self.calls.append({"query": query, "context_docs": context_docs})
        return f"Tìm thấy {context_docs[0]['name']} ({context_docs[0]['sku']})."

    def generate_stream(self, query: str, context_docs: list[dict[str, Any]]):
        self.calls.append({"query": query, "context_docs": context_docs})
        yield "Tìm thấy "
        yield f"{context_docs[0]['name']} ({context_docs[0]['sku']})."


def test_full_product_rag_pipeline(monkeypatch):
    search_engine = FakeSearchEngine()
    reranker = FakeReranker()
    generator = FakeGenerator()
    monkeypatch.setattr(
        orchestrator,
        "_components",
        (search_engine, reranker, generator),
    )
    metadata = {
        "category": "gia-dung/may-loc-khong-khi",
        "in_stock_only": True,
        "min_price": None,
        "max_price": 9_999_999,
        "room_area_m2": None,
    }
    monkeypatch.setattr(
        orchestrator,
        "route",
        lambda _query: {
            "intent": "product",
            "collection": "products",
            "metadata": metadata,
            "early_response": None,
        },
    )
    from src.tools import tool_repository

    live_filter = []

    def filter_candidates(documents, **filters):
        live_filter.append(filters)
        return documents

    monkeypatch.setattr(
        tool_repository,
        "filter_catalog_candidates",
        filter_candidates,
    )

    answer = orchestrator.process_raw_query(
        "Mình muốn mua máy lọc không khí AirPure giá dưới 10 triệu trong kho"
    )

    assert answer == "Tìm thấy Máy lọc không khí AirPure X (SKU-AP-X)."
    assert search_engine.calls == [
        {
            "query": "Mình muốn mua máy lọc không khí AirPure giá dưới 10 triệu trong kho",
            "top_k": 30,
            "category": "gia-dung/may-loc-khong-khi",
        }
    ]
    assert live_filter == [
        {
            "min_price_vnd": None,
            "max_price_vnd": 9_999_999,
            "in_stock_only": True,
        }
    ]
    assert reranker.calls[0]["top_n"] == 5
    assert reranker.calls[0]["documents"][0]["sku"] == "SKU-AP-X"
    assert (
        generator.calls[0]["context_docs"][0]["category"]
        == "gia-dung/may-loc-khong-khi"
    )


def test_streaming_pipeline_forwards_generator_chunks(monkeypatch):
    search_engine = FakeSearchEngine()
    reranker = FakeReranker()
    generator = FakeGenerator()
    monkeypatch.setattr(
        orchestrator,
        "_components",
        (search_engine, reranker, generator),
    )
    monkeypatch.setattr(
        orchestrator,
        "route",
        lambda _query: {
            "intent": "product",
            "collection": "products",
            "metadata": {
                "category": "gia-dung/may-loc-khong-khi",
                "in_stock_only": True,
                "min_price": None,
                "max_price": 9_999_999,
                "room_area_m2": None,
            },
            "early_response": None,
        },
    )
    from src.tools import tool_repository

    monkeypatch.setattr(
        tool_repository,
        "filter_catalog_candidates",
        lambda documents, **_filters: documents,
    )

    chunks = list(
        orchestrator.process_raw_query_stream(
            "Mình muốn mua máy lọc không khí AirPure giá dưới 10 triệu trong kho"
        )
    )

    assert chunks == [
        "Tìm thấy ",
        "Máy lọc không khí AirPure X (SKU-AP-X).",
    ]
    assert len(search_engine.calls) == 1
    assert len(reranker.calls) == 1


def test_room_area_metadata_filters_products_by_supported_coverage(monkeypatch):
    engine = FakeSearchEngine()
    assert (
        orchestrator._retrieve_documents(
            engine,
            "máy lọc không khí",
            {
                "collection": "products",
                "metadata": {"room_area_m2": 30, "category": None},
            },
        )
        == []
    )

    assert orchestrator._supports_room_area(
        {"attributes": {"room_area_m2": 30}},
        30,
    )
    assert not orchestrator._supports_room_area(
        {"attributes": {"room_area_m2": 25}},
        30,
    )
