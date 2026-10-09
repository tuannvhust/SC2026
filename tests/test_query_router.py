from src.memory.semantic_rag.query_router import route


def test_product_filters_match_catalog_payload_values():
    result = route("Mình muốn mua máy lọc không khí giá dưới 10 triệu trong kho")

    assert result["intent"] == "product"
    assert result["collection"] == "products"
    assert result["metadata"] == {
        "category": "gia-dung/may-loc-khong-khi",
        "in_stock_only": True,
        "min_price": None,
        "max_price": 10_000_000,
    }


def test_router_recognizes_current_catalog_product_categories():
    assert route("Tìm giày size 42")["metadata"]["category"] == "thoi-trang/giay"
    assert route("Mua máy lọc nước Karofi")["metadata"]["category"] == "gia-dung/may-loc-nuoc"
    assert route("Sản phẩm mẹ bé")["metadata"]["category"] == "me-be"
    assert route("Tìm tất thể thao")["metadata"]["category"] == "thoi-trang/phu-kien"
    assert route("Có combo nào?")["metadata"]["category"] == "gia-dung/combo"


def test_policy_query_selects_policy_collection():
    result = route("Chính sách bảo hành điện thoại thế nào?")

    assert result["intent"] == "policy"
    assert result["collection"] == "policies"
