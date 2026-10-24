from src.memory.semantic_rag import orchestrator


def test_process_raw_query_returns_early_response_without_initializing_search(
    monkeypatch,
):
    early_response = "Chào anh/chị! Em có thể giúp gì cho bạn hôm nay?"
    monkeypatch.setattr(
        orchestrator,
        "route",
        lambda _query: {
            "intent": "smalltalk",
            "collection": None,
            "metadata": {
                "category": None,
                "in_stock_only": False,
                "min_price": None,
                "max_price": None,
                "room_area_m2": None,
            },
            "early_response": early_response,
        },
    )

    assert orchestrator.process_raw_query("Xin chào") == early_response


def test_product_query_is_routed_to_products(monkeypatch):
    from types import SimpleNamespace

    from src.memory.semantic_rag import query_router

    extraction = query_router.QueryRouteExtraction(
        intent="product",
        collection="products",
        metadata=query_router.QueryMetadata(
            category="gia-dung/may-loc-khong-khi",
            in_stock_only=False,
            min_price=None,
            max_price=None,
            room_area_m2=None,
        ),
        early_response=None,
    )
    monkeypatch.setattr(
        query_router,
        "_get_structured_router",
        lambda: SimpleNamespace(invoke=lambda _messages: extraction),
    )

    result = query_router.route("Mình muốn mua máy lọc không khí AirPure")

    assert result["intent"] == "product"
    assert result["collection"] == "products"
    assert result["metadata"]["category"] == "gia-dung/may-loc-khong-khi"
