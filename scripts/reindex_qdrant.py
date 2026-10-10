"""
scripts/reindex_qdrant.py
Khởi tạo lại toàn bộ Vector Store Qdrant từ dữ liệu thật:
1. data/catalog/products.json -> Collection 'products'
2. data/policy/*.md          -> Collection 'policies' (chunk theo các mã mục [DT-xx], [BH-xx], [VC-xx]...)

Chạy lệnh:
    $env:PYTHONUTF8=1; python scripts/reindex_qdrant.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

# UTF-8 cho console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.services.vector_store import QdrantVectorStore
from src.services.gemini_embedder import GeminiDenseEmbedder
from src.services.bm25s_embedder import BM25SparseEmbedder

DATA_DIR = ROOT / "data"
CATALOG_DIR = DATA_DIR / "catalog"
POLICY_DIR = DATA_DIR / "policy"
PROCESSED_DIR = DATA_DIR / "processed"


def prepare_products() -> List[Dict[str, Any]]:
    """Đọc và chuẩn hóa dữ liệu từ data/catalog/products.json."""
    products_file = CATALOG_DIR / "products.json"
    if not products_file.exists():
        print(f"❌ Không tìm thấy file {products_file}")
        return []

    data = json.loads(products_file.read_text(encoding="utf-8"))
    raw_products = data.get("products", data) if isinstance(data, dict) else data

    docs = []
    for p in raw_products:
        sku = p.get("sku", "")
        name = p.get("name", "")
        cat = p.get("category", "")
        brand = p.get("brand", "")
        price = p.get("list_price_vnd", 0)
        stock = p.get("stock", 0)
        attrs = p.get("attributes", {})

        attr_parts = []
        if "room_area_m2" in attrs:
            attr_parts.append(f"diện tích phòng phù hợp {attrs['room_area_m2']} m2")
        if "features" in attrs:
            attr_parts.append(f"tính năng: {attrs['features']}")
        if "warranty_months" in attrs:
            attr_parts.append(f"bảo hành chính hãng {attrs['warranty_months']} tháng")
        if "child_safe_lock" in attrs:
            attr_parts.append("có khóa trẻ em" if attrs["child_safe_lock"] else "không có khóa trẻ em")

        attr_text = "; ".join(attr_parts) if attr_parts else "tiêu chuẩn"
        price_fmt = f"{price:,}đ".replace(",", ".")
        stock_str = f"còn hàng ({stock} sản phẩm)" if stock > 0 else "hết hàng"

        embedding_text = (
            f"Sản phẩm {name} (Mã SKU: {sku}) thuộc danh mục {cat}, thương hiệu {brand}. "
            f"Giá niêm yết: {price_fmt}, tình trạng: {stock_str}. "
            f"Thông số & tính năng: {attr_text}."
        )

        docs.append({
            "_id": sku,
            "sku": sku,
            "name": name,
            "category": cat,
            "brand": brand,
            "list_price_vnd": price,
            "min_price": price,
            "max_price": price,
            "in_stock": stock > 0,
            "stock": stock,
            "attributes": attrs,
            "variants": p.get("variants", []),
            "embedding_text": embedding_text,
        })

    return docs


def prepare_policies() -> List[Dict[str, Any]]:
    """Đọc các file markdown từ data/policy/ và chunk theo đề mục [MÃ-SỐ]."""
    docs = []
    for path in POLICY_DIR.glob("*.md"):
        fname = path.name
        # Bỏ qua tài liệu nội bộ, nội quy, hoặc hết hiệu lực
        if "NOI-BO" in fname.upper() or "noi-quy" in fname.lower() or "HET-HIEU-LUC" in fname.upper():
            continue

        raw_text = path.read_text(encoding="utf-8")

        # Tách các section dạng: ## [MÃ] Tiêu đề
        sections = re.split(r"(?m)^##\s+", raw_text)
        doc_header = sections[0].strip() if sections else ""
        header_title = doc_header.split("\n")[0].lstrip("#").strip() if doc_header else path.stem

        if len(sections) > 1:
            for sec in sections[1:]:
                lines = sec.strip().split("\n")
                heading = lines[0].strip()
                body = "\n".join(lines[1:]).strip()

                # Trích xuất mã [DT-01], [BH-01]... nếu có
                m = re.match(r"\[([A-Za-z0-9_-]+)\]\s*(.*)", heading)
                if m:
                    chunk_id = m.group(1)
                    title = f"{header_title} - {m.group(2).strip()}"
                else:
                    chunk_id = f"{path.stem}_{abs(hash(heading)) % 10000}"
                    title = f"{header_title} - {heading}"

                embedding_text = f"Tài liệu '{title}' ({fname}):\n{body}"
                docs.append({
                    "_id": chunk_id,
                    "chunk_id": chunk_id,
                    "policy_id": chunk_id,
                    "title": title,
                    "source": fname,
                    "content": body,
                    "embedding_text": embedding_text,
                })
        else:
            # File ngắn không có mục con
            docs.append({
                "_id": path.stem,
                "chunk_id": path.stem,
                "policy_id": path.stem,
                "title": header_title,
                "source": fname,
                "content": raw_text,
                "embedding_text": f"Tài liệu '{header_title}':\n{raw_text}",
            })

    return docs


def parallel_embed_corpus(
    texts: List[str],
    dense_embedder: GeminiDenseEmbedder,
    sparse_embedder: BM25SparseEmbedder,
    save_dir: str
):
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_dense = executor.submit(dense_embedder.embed_batch, texts)
        f_sparse = executor.submit(sparse_embedder.fit_corpus, texts, save_dir)
        return f_dense.result(), f_sparse.result()


def main():
    print("=" * 70)
    print("KHỞI TẠO LẠI TOÀN BỘ VECTOR STORE QDRANT TỪ DỮ LIỆU THẬT")
    print("=" * 70)

    # 1. Chuẩn bị dữ liệu
    print("\n[1/4] Chuẩn hóa dữ liệu từ products.json và data/policy/*.md...")
    products = prepare_products()
    policies = prepare_policies()
    print(f"   -> Đã tải {len(products)} sản phẩm từ data/catalog/products.json")
    print(f"   -> Đã chia thành {len(policies)} chunks chính sách từ data/policy/*.md")

    # Lưu bản backup vào data/processed
    PROCESSED_DIR.mkdir(exist_ok=True)
    with open(PROCESSED_DIR / "products_normalized.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    with open(PROCESSED_DIR / "policies_normalized.json", "w", encoding="utf-8") as f:
        json.dump(policies, f, ensure_ascii=False, indent=2)

    # 2. Khởi tạo Qdrant Store và XÓA SẠCH COLLECTIONS CŨ
    print("\n[2/4] Đặt lại (Reset) Collections trong Qdrant...")
    store = QdrantVectorStore()
    store.init_collection("products", recreate=True)
    store.init_collection("policies", recreate=True)

    dense_embedder = GeminiDenseEmbedder()
    sparse_prod_embedder = BM25SparseEmbedder()
    sparse_pol_embedder = BM25SparseEmbedder()

    bm25_prod_dir = str(PROCESSED_DIR / "bm25_products")
    bm25_pol_dir = str(PROCESSED_DIR / "bm25_policies")

    # 3. Tạo Embeddings và Upsert Products
    print("\n[3/4] Xử lý nhúng & nạp 40 sản phẩm thật vào Qdrant...")
    prod_texts = [p["embedding_text"] for p in products]
    p_dense, p_sparse = parallel_embed_corpus(prod_texts, dense_embedder, sparse_prod_embedder, bm25_prod_dir)
    store.upsert_catalog_documents("products", products, p_dense, p_sparse)

    # 4. Tạo Embeddings và Upsert Policies
    print("\n[4/4] Xử lý nhúng & nạp các chunks chính sách thật vào Qdrant...")
    pol_texts = [pol["embedding_text"] for pol in policies]
    pol_dense, pol_sparse = parallel_embed_corpus(pol_texts, dense_embedder, sparse_pol_embedder, bm25_pol_dir)
    store.upsert_catalog_documents("policies", policies, pol_dense, pol_sparse)

    print("\n" + "=" * 70)
    print(" HOÀN TẤT: Qdrant đã được nạp 100% dữ liệu thật thành công!")
    print("=" * 70)


if __name__ == "__main__":
    main()

