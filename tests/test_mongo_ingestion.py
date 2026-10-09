"""Test normalization for the current products.json catalog schema."""

from src.memory.semantic_rag.ingestion import ingest_product_document


def test_ingest_product_document_uses_catalog_schema():
    product = {
        "sku": "SKU-SN-TEST",
        "name": "Giày chạy bộ",
        "category": "thoi-trang/giay",
        "brand": "RunLite",
        "list_price_vnd": 1_290_000,
        "attributes": {"material": "vải lưới", "return_days": 7},
        "stock": 12,
        "variants": [
            {
                "variant_sku": "SKU-SN-TEST-42-DEN",
                "size": 42,
                "color": "đen",
                "price_delta_vnd": 50_000,
                "stock": 4,
            }
        ],
    }

    prepared = ingest_product_document(product)

    assert prepared["_id"] == "SKU-SN-TEST"
    assert prepared["variants"] == [
        {
            "variant_sku": "SKU-SN-TEST-42-DEN",
            "size": 42,
            "color": "đen",
        }
    ]
    assert not {
        "list_price_vnd",
        "min_price",
        "max_price",
        "stock",
        "total_stock",
        "in_stock",
    } & prepared.keys()
    assert "1.290.000đ" not in prepared["embedding_text"]
    assert "tồn kho" not in prepared["embedding_text"]
    assert "SKU-SN-TEST-42-DEN" in prepared["embedding_text"]
    assert "vải lưới" in prepared["embedding_text"]
    assert not {"price_delta_vnd", "stock"} & prepared["variants"][0].keys()
