"""Normalize catalog products and prepare text and metadata for vector search."""

from typing import Any, Dict

from src.memory.semantic_rag.payload import sanitize_product_payload


ATTRIBUTE_LABELS = {
    "room_area_m2": "Diện tích phòng",
    "features": "Tính năng",
    "warranty_months": "Bảo hành",
    "child_safe_lock": "Khóa an toàn trẻ em",
    "stages": "Số lõi lọc",
    "material": "Chất liệu",
    "return_days": "Thời hạn đổi trả",
    "max_weight_kg": "Tải trọng tối đa",
    "volume_ml": "Dung tích",
    "discontinued": "Ngừng kinh doanh",
    "successor_sku": "SKU thay thế",
    "bundle_of": "Combo gồm SKU",
    "saving_vnd": "Tiết kiệm",
}


def format_price(value: int) -> str:
    return f"{value:,.0f}đ".replace(",", ".")


def generate_product_embedding_text(product: Dict[str, Any]) -> str:
    """Build searchable Vietnamese text from the products.json product schema."""
    sku = str(product["sku"])
    name = str(product.get("name") or sku)
    category = str(product.get("category") or "")
    brand = str(product.get("brand") or "")
    parts = [f"{category} {name} (SKU: {sku}), thương hiệu {brand}."]

    attributes = product.get("attributes") or {}
    if attributes:
        details = []
        for key, value in attributes.items():
            label = ATTRIBUTE_LABELS.get(key, key.replace("_", " "))
            if isinstance(value, bool):
                value = "có" if value else "không"
            elif isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            elif key == "saving_vnd":
                value = format_price(value)
            elif key == "warranty_months":
                value = f"{value} tháng"
            elif key == "max_weight_kg":
                value = f"{value} kg"
            elif key == "volume_ml":
                value = f"{value} ml"
            elif key == "room_area_m2":
                value = f"{value} m²"
            details.append(f"{label}: {value}")
        parts.append("Thông tin sản phẩm: " + ", ".join(details) + ".")

    variants = product.get("variants") or []
    variant_details = []
    for variant in variants:
        details = []
        if variant.get("variant_sku"):
            details.append(f"SKU {variant['variant_sku']}")
        if variant.get("size") is not None:
            details.append(f"size {variant['size']}")
        if variant.get("color"):
            details.append(f"màu {variant['color']}")

        if details:
            variant_details.append(", ".join(details))
    if variant_details:
        parts.append("Các phiên bản: " + "; ".join(variant_details) + ".")

    return " ".join(parts)


def ingest_product_document(product: Dict[str, Any]) -> Dict[str, Any]:
    """Add search metadata to a product using the current catalog field names."""
    sku = product.get("sku")
    if not sku:
        raise ValueError("Product must include a 'sku'.")

    normalized = {
        **product,
        "sku": str(sku),
        "_id": str(sku),
    }
    normalized["embedding_text"] = generate_product_embedding_text(normalized)
    return sanitize_product_payload(normalized)
