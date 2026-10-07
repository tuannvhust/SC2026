from src.memory.semantic_rag.orchestrator import process_raw_query


def test_process_raw_query_returns_early_response_without_initializing_search():
    assert process_raw_query("Xin chào") == "Chào anh/chị! Em có thể giúp gì cho bạn hôm nay?"


def test_product_query_is_routed_to_products():
    from src.memory.semantic_rag.query_router import route

    result = route("Mình muốn mua máy lọc không khí AirPure")

    assert result["intent"] == "product"
    assert result["collection"] == "products"
    assert result["metadata"]["category"] == "gia-dung/may-loc-khong-khi"
