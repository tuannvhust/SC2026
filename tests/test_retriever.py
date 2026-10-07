from unittest.mock import Mock

from src.memory.semantic_rag.retriever import SemanticRetriever


def test_retriever_passes_product_filters_to_search_engine():
    engine = Mock()
    engine.search_products.return_value = [{"sku": "SKU-AP-X"}]
    retriever = SemanticRetriever(engine)

    result = retriever.search_products(
        "AirPure",
        top_k=5,
        category="gia-dung/may-loc-khong-khi",
        in_stock_only=True,
        min_price=5_000_000,
        max_price=10_000_000,
    )

    assert result == [{"sku": "SKU-AP-X"}]
    engine.search_products.assert_called_once_with(
        query="AirPure",
        top_k=5,
        category="gia-dung/may-loc-khong-khi",
        in_stock_only=True,
        min_price=5_000_000,
        max_price=10_000_000,
    )
