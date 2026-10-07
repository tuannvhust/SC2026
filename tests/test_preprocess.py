import json

from src.memory.semantic_rag.chunker import MarkdownChunker
from src.memory.semantic_rag.preprocess import _index_collection, _load_product


def _product(sku, **fields):
    return {
        "sku": sku,
        "name": f"Product {sku}",
        "category": "gia-dung/may-loc-khong-khi",
        "brand": "Brand",
        "list_price_vnd": 1000,
        "attributes": {"features": "HEPA filter", "warranty_months": 12},
        "stock": 3,
        "variants": [],
        **fields,
    }


def test_load_product_creates_full_document_per_catalog_entry(tmp_path):
    path = tmp_path / "products.json"
    path.write_text(
        json.dumps(
            {
                "reference_date": "2026-10-15",
                "currency": "VND",
                "products": [
                    _product(
                        "SKU-1",
                        variants=[
                            {
                                "variant_sku": "SKU-1-RED",
                                "color": "red",
                                "price_delta_vnd": 50,
                                "stock": 2,
                            }
                        ],
                    ),
                    _product("SKU-2"),
                ],
            }
        ),
        encoding="utf-8",
    )

    documents = _load_product(path)

    assert len(documents) == 2
    assert documents[0]["meta"]["sku"] == "SKU-1"
    assert documents[0]["meta"]["min_price"] == 1000
    assert documents[0]["meta"]["max_price"] == 1050
    assert documents[0]["meta"]["total_stock"] == 3
    assert documents[0]["meta"]["attributes"]["features"] == "HEPA filter"
    assert "SKU-1-RED" in documents[0]["text"]
    assert "Bảo hành: 12 tháng" in documents[0]["text"]
    assert documents[1]["meta"]["sku"] == "SKU-2"


def test_index_collection_upserts_each_product_with_stable_sku_id(tmp_path):
    path = tmp_path / "products.json"
    path.write_text(
        json.dumps({"products": [_product("SKU-1"), _product("SKU-2")]}),
        encoding="utf-8",
    )

    class Embedder:
        index_dir = None

        def embed_text(self, text):
            return [float(len(text))]

        def fit_corpus(self, texts, save_dir=None):
            self.corpus = texts
            return [
                {"indices": [index], "values": [1.0]}
                for index, _ in enumerate(texts)
            ]

    class Store:
        def upsert_catalog_documents(self, collection, documents, dense, sparse):
            self.collection = collection
            self.documents = documents
            self.dense = dense
            self.sparse = sparse

    store = Store()
    _index_collection("products", [path], Embedder(), Embedder(), store)

    assert store.collection == "products"
    assert [document["_id"] for document in store.documents] == ["SKU-1", "SKU-2"]
    assert all(document["embedding_text"].startswith("# Product") for document in store.documents)
    assert len(store.documents) == len(store.dense) == len(store.sparse)


def test_real_catalog_products_are_normalized_for_current_schema():
    from pathlib import Path

    from src.memory.semantic_rag.ingestion import ingest_product_document

    catalog = json.loads(
        Path("data/catalog/products.json").read_text(encoding="utf-8")
    )
    normalized = [
        ingest_product_document(product)
        for product in catalog["products"]
    ]

    airpure = next(
        product for product in normalized if product["sku"] == "SKU-AP-X"
    )
    sneaker = next(
        product for product in normalized if product["sku"] == "SKU-SN-RUN1"
    )
    assert len(normalized) == 40
    assert airpure["min_price"] == airpure["max_price"] == 4_890_000
    assert airpure["total_stock"] == 40
    assert "HEPA H13" in airpure["embedding_text"]
    assert "Bảo hành: 24 tháng" in airpure["embedding_text"]
    assert sneaker["min_price"] == 1_290_000
    assert sneaker["max_price"] == 1_340_000
    assert sneaker["total_stock"] == 48
    assert "size 43" in sneaker["embedding_text"]
    assert "SKU-SN-RUN1-43-DEN" in sneaker["embedding_text"]


def test_policy_chunk_keeps_heading_and_section_code():
    chunks = MarkdownChunker().chunk(
        "## [DT-01] Thời hạn đổi trả\n\nKhách được đổi trả trong 7 ngày.",
        {"source_path": "data/policy/chinh-sach-doi-tra.md", "type": "policy"},
    )

    assert len(chunks) == 1
    assert chunks[0]["id"] == "DT-01"
    assert chunks[0]["meta"]["chunk_id"] == "DT-01"
    assert chunks[0]["text"].startswith("## [DT-01] Thời hạn đổi trả")
    assert "7 ngày" in chunks[0]["text"]
