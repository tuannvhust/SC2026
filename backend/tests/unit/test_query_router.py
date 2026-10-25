import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from src.memory.semantic_rag import query_router
from src.memory.semantic_rag.query_router import (
    CATEGORY_GUIDE,
    QueryMetadata,
    QueryRouteExtraction,
)


def _extraction(
    *,
    intent="product",
    collection="products",
    category="gia-dung/may-loc-khong-khi",
    in_stock_only=False,
    min_price=None,
    max_price=None,
    room_area_m2=None,
    early_response=None,
    min_price_exclusive=False,
    max_price_exclusive=False,
):
    return QueryRouteExtraction(
        intent=intent,
        collection=collection,
        metadata=QueryMetadata(
            category=category,
            in_stock_only=in_stock_only,
            min_price=min_price,
            max_price=max_price,
            room_area_m2=room_area_m2,
            min_price_exclusive=min_price_exclusive,
            max_price_exclusive=max_price_exclusive,
        ),
        early_response=early_response,
    )


def test_structured_router_uses_groq_function_calling_fallback(monkeypatch):
    from src import config

    primary_chain = Mock()
    fallback_chain = Mock()
    primary_model = Mock(
        with_structured_output=Mock(return_value=primary_chain)
    )
    groq_model = Mock(
        with_structured_output=Mock(return_value=fallback_chain)
    )
    monkeypatch.setattr(config, "llm", primary_model)
    monkeypatch.setattr(config, "groq_llm", groq_model)

    router = query_router._get_structured_router()

    primary_model.with_structured_output.assert_called_once_with(
        QueryRouteExtraction,
        method="json_schema",
    )
    groq_model.with_structured_output.assert_called_once_with(
        QueryRouteExtraction,
        method="function_calling",
    )
    primary_chain.with_fallbacks.assert_called_once_with([fallback_chain])
    assert router is primary_chain.with_fallbacks.return_value


@pytest.mark.parametrize(
    ("spoken_limit", "exclusive", "expected"),
    [
        (5_000_000, True, 4_999_999),
        (5_000_000, False, 5_000_000),
    ],
)
def test_route_preserves_exclusive_and_inclusive_vnd_upper_bounds(
    monkeypatch, spoken_limit, exclusive, expected
):
    extraction = _extraction(
        max_price=spoken_limit,
        max_price_exclusive=exclusive,
    )
    invoke = Mock(return_value=extraction)
    monkeypatch.setattr(
        query_router,
        "_get_structured_router",
        lambda: Mock(invoke=invoke),
    )

    result = query_router.route("Có máy lọc khí dưới 5 củ không?")

    assert result["metadata"]["max_price"] == expected
    assert result["metadata"]["min_price"] is None
    assert invoke.call_args.args[0][-1] == ("human", "Có máy lọc khí dưới 5 củ không?")


def test_route_extracts_all_required_product_metadata(monkeypatch):
    extraction = _extraction(
        in_stock_only=True,
        max_price=5_000_000,
        room_area_m2=30,
    )
    monkeypatch.setattr(
        query_router,
        "_get_structured_router",
        lambda: Mock(invoke=Mock(return_value=extraction)),
    )

    result = query_router.route(
        "Phòng 30m² thì nên tìm máy lọc nào, ngân sách tối đa 5 triệu còn hàng?"
    )

    assert result == {
        "intent": "product",
        "collection": "products",
        "metadata": {
            "category": "gia-dung/may-loc-khong-khi",
            "in_stock_only": True,
            "min_price": None,
            "max_price": 5_000_000,
            "room_area_m2": 30,
        },
        "early_response": None,
    }


def test_router_schema_restricts_categories_to_all_project_catalog_categories():
    schema = QueryRouteExtraction.model_json_schema()
    categories = (
        schema["$defs"]["QueryMetadata"]["properties"]["category"]["anyOf"][0][
            "enum"
        ]
    )

    assert set(categories) == set(CATEGORY_GUIDE)
    assert {
        "gia-dung/combo",
        "gia-dung/may-loc-khong-khi",
        "gia-dung/may-loc-nuoc",
        "gia-dung/noi-chien",
        "gia-dung/phu-kien",
        "gia-dung/quat",
        "me-be",
        "thoi-trang/ao-khoac",
        "thoi-trang/giay",
        "thoi-trang/phu-kien",
    } == set(categories)
    catalog_path = (
        Path(__file__).resolve().parents[3] / "data" / "catalog" / "products.json"
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    project_categories = {
        item["category"]
        for item in catalog["products"]
        if item.get("category")
    }
    assert project_categories == set(categories)


def test_route_returns_early_response_for_smalltalk(monkeypatch):
    extraction = _extraction(
        intent="smalltalk",
        collection=None,
        category=None,
        early_response="Chào anh/chị, em có thể giúp gì ạ?",
    )
    monkeypatch.setattr(
        query_router,
        "_get_structured_router",
        lambda: Mock(invoke=Mock(return_value=extraction)),
    )

    result = query_router.route("Chào bạn")

    assert result["intent"] == "smalltalk"
    assert result["collection"] is None
    assert result["early_response"] == "Chào anh/chị, em có thể giúp gì ạ?"


@pytest.mark.parametrize(
    "response",
    [
        {"intent": "product"},
        {
            "intent": "product",
            "collection": "products",
            "metadata": {
                "category": "invented/category",
                "in_stock_only": False,
                "min_price": None,
                "max_price": None,
                "room_area_m2": None,
            },
            "early_response": None,
        },
        {
            "intent": "product",
            "collection": "products",
            "metadata": {
                "category": None,
                "in_stock_only": False,
                "min_price": "500000",
                "max_price": None,
                "room_area_m2": None,
            },
            "early_response": None,
        },
    ],
)
def test_route_rejects_invalid_or_unusable_structured_output(monkeypatch, response):
    monkeypatch.setattr(
        query_router,
        "_get_structured_router",
        lambda: Mock(invoke=Mock(return_value=response)),
    )

    result = query_router.route("Mình muốn hỏi về một sản phẩm")

    assert result["status"] == "error"
    assert result["intent"] is None
    assert result["collection"] is None
    assert result["metadata"] is None
    assert "thử lại" in result["early_response"]


def test_route_surfaces_gemini_api_failure_without_fabricating_metadata(monkeypatch):
    invoke = Mock(side_effect=TimeoutError("request timed out"))
    monkeypatch.setattr(
        query_router,
        "_get_structured_router",
        lambda: Mock(invoke=invoke),
    )

    result = query_router.route("Sản phẩm nào phù hợp?")

    assert result["status"] == "error"
    assert result["metadata"] is None
    assert result["error"] == "query routing unavailable (TimeoutError)."


def test_intent_collection_must_be_consistent():
    with pytest.raises(ValidationError):
        _extraction(intent="policy", collection="products", category=None)
