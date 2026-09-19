from src.memory.semantic_rag.query_router import route


def test_product_filters_match_catalog_payload_values():
    result = route("Mình muốn mua điện thoại Samsung giá dưới 10 triệu trong kho")

    assert result["intent"] == "product"
    assert result["collection"] == "products"
    assert result["metadata"] == {
        "category": "dien_thoai",
        "in_stock_only": True,
        "min_price": None,
        "max_price": 10_000_000,
    }


def test_policy_query_selects_policy_collection():
    result = route("Chính sách bảo hành điện thoại thế nào?")

    assert result["intent"] == "policy"
    assert result["collection"] == "policies"
