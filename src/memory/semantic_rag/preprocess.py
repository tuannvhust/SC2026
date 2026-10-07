import json
from pathlib import Path
from typing import List, Dict, Any

from src.memory.semantic_rag.chunker import MarkdownChunker
from src.memory.semantic_rag.ingestion import ingest_product_document
from src.services.vector_store import QdrantVectorStore
from src.services.gemini_embedder import GeminiDenseEmbedder
from src.services.bm25s_embedder import BM25SparseEmbedder

DATA_ROOT = Path("data")
POLICY_ROOT = DATA_ROOT / "policy"
PRODUCT_ROOT = DATA_ROOT / "catalog"


def _build_base_meta(path: Path, doc_type: str) -> Dict[str, Any]:
    """Build base metadata for a document from its filename."""
    name_lower = path.name.lower()
    return {
        "source_path": str(path),
        "type": doc_type,
        "is_active": "het-hieu-luc" not in name_lower,
        "access_level": "restricted" if "noi-bo" in name_lower else "public",
    }


def _load_policy(path: Path) -> Dict[str, Any]:
    """Load a markdown policy file and extract its metadata."""
    text = path.read_text(encoding="utf-8")
    meta = _build_base_meta(path, "policy")
    meta.update({
        "policy_id": path.stem,
        "title": path.stem.replace("-", " ").title(),
    })
    return {"text": text, "meta": meta}


def _load_product(path: Path) -> List[Dict[str, Any]]:
    """Load a product catalog and create a chunkable document for each product."""
    data = json.loads(path.read_text(encoding="utf-8"))
    products = data.get("products")
    if not isinstance(products, list):
        raise ValueError(f"Expected a 'products' list in {path}")

    documents = []
    for product in products:
        if not isinstance(product, dict):
            raise ValueError(f"Expected each product to be an object in {path}")

        enriched_product = ingest_product_document(product)
        sku = enriched_product["sku"]
        name = str(enriched_product.get("name") or sku)

        meta = {
            **_build_base_meta(path, "product"),
            **enriched_product,
            "sku": sku,
            "title": name,
            "is_active": (
                "het-hieu-luc" not in path.name.lower()
                and not enriched_product.get("attributes", {}).get(
                    "discontinued", False
                )
            ),
        }
        raw_text = f"# {name} (SKU: {sku})\n\n{enriched_product['embedding_text']}"
        documents.append({"text": raw_text, "meta": meta})

    return documents


def _index_collection(
    collection_name: str,
    files: List[Path],
    dense_embedder: GeminiDenseEmbedder,
    sparse_embedder: BM25SparseEmbedder,
    store: QdrantVectorStore,
) -> None:
    """Chunk, embed, and upsert a list of files into a target Qdrant collection."""
    chunker = MarkdownChunker()
    load_fn = _load_policy if collection_name == "policies" else _load_product
    payloads = []
    dense_vectors = []

    for file_path in files:
        loaded = load_fn(file_path)
        documents = loaded if isinstance(loaded, list) else [loaded]
        for doc in documents:
            for ch in chunker.chunk(doc["text"], doc["meta"]):
                chunk_meta = ch["meta"]
                sku = chunk_meta.get("sku")
                chunk_index = chunk_meta["chunk_index"]
                point_key = (
                    sku if collection_name == "products" and chunk_index == 0
                    else f"{sku}:chunk:{chunk_index}"
                    if collection_name == "products"
                    else ch["id"]
                )
                payloads.append({
                    **chunk_meta,
                    "_id": point_key,
                    "chunk_id": chunk_meta["chunk_id"],
                    "embedding_text": ch["text"],
                })
                dense_vectors.append(dense_embedder.embed_text(ch["text"]))

    if payloads:
        sparse_vectors = sparse_embedder.fit_corpus(
            [payload["embedding_text"] for payload in payloads],
            save_dir=sparse_embedder.index_dir,
        )

        store.upsert_catalog_documents(
            collection_name, payloads, dense_vectors, sparse_vectors
        )
        print(f"[SUCCESS] Indexed {len(payloads)} chunks → {collection_name}")


def main() -> None:
    store = QdrantVectorStore()
    dense = GeminiDenseEmbedder()
    
    sparse_pol = BM25SparseEmbedder(index_dir="data/processed/bm25_policies")
    sparse_prod = BM25SparseEmbedder(index_dir="data/processed/bm25_products")

    # Index Policies
    policy_files = list(POLICY_ROOT.glob("*.md"))
    _index_collection("policies", policy_files, dense, sparse_pol, store)

    # Index Products
    product_files = list(PRODUCT_ROOT.glob("products*.json"))
    _index_collection("products", product_files, dense, sparse_prod, store)

    print("[SUCCESS] Pre-processing completed – Qdrant collections are up-to-date.")


if __name__ == "__main__":
    main()