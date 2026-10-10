"""End-to-end local test for the semantic RAG orchestration pipeline."""

from dataclasses import dataclass, field
from typing import Any

from src.memory.semantic_rag import orchestrator


@dataclass
class FakeSearchEngine:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def search_products(self, query: str, top_k: int, category: str | None,
                        in_stock_only: bool, min_price: int | None,
                        max_price: int | None) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "category": category,
                "in_stock_only": in_stock_only,
                "min_price": min_price,
                "max_price": max_price,
            }
        )
        return [
            {
                "sku": "SKU-PH-A55-128",
                "name": "Samsung Galaxy A55 5G",
                "category": "dien_thoai",
                "in_stock": True,
                "min_price": 9_490_000,
                "embedding_text": "Samsung Galaxy A55 5G",
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


def test_full_product_rag_pipeline(monkeypatch):
    search_engine = FakeSearchEngine()
    reranker = FakeReranker()
    generator = FakeGenerator()
    monkeypatch.setattr(
        orchestrator,
        "_components",
        (search_engine, reranker, generator),
    )

    answer = orchestrator.process_raw_query(
        "Mình muốn mua điện thoại Samsung giá dưới 10 triệu trong kho"
    )

    assert answer == "Tìm thấy Samsung Galaxy A55 5G (SKU-PH-A55-128)."
    assert search_engine.calls == [
        {
            "query": "Mình muốn mua điện thoại Samsung giá dưới 10 triệu trong kho",
            "top_k": 5,
            "category": "dien_thoai",
            "in_stock_only": True,
            "min_price": None,
            "max_price": 10_000_000,
        }
    ]
    assert reranker.calls[0]["top_n"] == 5
    assert reranker.calls[0]["documents"][0]["sku"] == "SKU-PH-A55-128"
    assert generator.calls[0]["context_docs"][0]["category"] == "dien_thoai"
