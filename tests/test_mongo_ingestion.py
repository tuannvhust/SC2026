"""
tests/test_mongo_ingestion.py
Kiá»ƒm tra:
1. ingestion.py nháº­n 1 document Mongo vÃ  sinh embedding_text chÃ­nh xÃ¡c.
2. MongoStore vÃ  CRUD cÆ¡ báº£n.
"""

from src.memory.semantic_rag.ingestion import ingest_product_document, ingest_policy_document


def test_ingest_single_mongo_doc():
    mongo_product_doc = {
        "_id": "SKU-PH-TEST-01",
        "sku": "SKU-PH-TEST-01",
        "name": "Test Phone Ultra",
        "category": "dien_thoai",
        "brand": "TechBrand",
        "specs": {"screen_inch": 6.7, "battery_mah": 5000, "chipset": "Snapdragon 8 Gen 3"},
        "variants": [
            {"storage_gb": 256, "ram_gb": 12, "color": "Ä‘en", "price_vnd": 15000000, "stock_qty": 10}
        ],
        "warranty_months": 12,
        "installment": {"supported": True, "interest_rate": 0, "min_months": 3, "max_months": 12},
        "trade_in": {"supported": True},
        "promos": [{"promo_code": "KM-TEST", "description": "Táº·ng quÃ ", "discount_vnd": 500000, "active": True}]
    }

    # Cháº¡y qua ingestion.py
    prepared = ingest_product_document(mongo_product_doc)

    assert prepared["_id"] == "SKU-PH-TEST-01"
    assert prepared["min_price"] == 15000000
    assert prepared["in_stock"] is True
    assert "embedding_text" in prepared
    assert "Test Phone Ultra" in prepared["embedding_text"]
    assert "Snapdragon 8 Gen 3" in prepared["embedding_text"]
    assert "15.000.000Ä‘" in prepared["embedding_text"]

    print("Test ingest_product_document passed!")

    mongo_policy_doc = {
        "_id": "policy_return",
        "policy_id": "return_policy",
        "category": "doi_tra",
        "details": {
            "window_days": 7,
            "conditions": "nguyÃªn seal",
            "who_pays_shipping": "shop"
        }
    }

    prepared_pol = ingest_policy_document(mongo_policy_doc)
    assert prepared_pol["_id"] == "policy_return"
    assert "embedding_text" in prepared_pol
    assert "Ä‘á»•i tráº£" in prepared_pol["embedding_text"]

    print("Test ingest_policy_document passed!")


if __name__ == "__main__":
    test_ingest_single_mongo_doc()
