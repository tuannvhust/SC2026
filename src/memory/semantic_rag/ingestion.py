"""Normalize catalog products and prepare text and metadata for vector search."""

from typing import Any, Dict


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

    list_price = product.get("list_price_vnd")
    if isinstance(list_price, (int, float)) and not isinstance(list_price, bool):
        list_price = int(list_price)
        parts.append(f"Giá niêm yết: {format_price(list_price)}.")
    else:
        list_price = None

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

        price_delta = variant.get("price_delta_vnd", 0)
        if list_price is not None:
            details.append(f"giá {format_price(list_price + price_delta)}")
        if variant.get("stock") is not None:
            details.append(f"tồn kho {variant['stock']}")
        variant_details.append(", ".join(details))
    if variant_details:
        parts.append("Các phiên bản: " + "; ".join(variant_details) + ".")

    stock = product.get("stock")
    if stock is not None:
        parts.append(
            f"Tồn kho: {stock}."
            if stock > 0
            else "Sản phẩm hiện hết hàng."
        )

    return " ".join(parts)


def ingest_product_document(product: Dict[str, Any]) -> Dict[str, Any]:
    """Add search metadata to a product using the current catalog field names."""
    doc = dict(product)
    sku = doc.get("sku")
    if not sku:
        raise ValueError("Product must include a 'sku'.")

    doc["sku"] = str(sku)
    doc["_id"] = str(sku)
    list_price = doc.get("list_price_vnd", 0)
    variants = doc.get("variants") or []
    prices = [list_price]
    prices.extend(
        list_price + variant.get("price_delta_vnd", 0)
        for variant in variants
    )
    doc["min_price"] = min(prices)
    doc["max_price"] = max(prices)
    doc["total_stock"] = doc.get("stock", 0)
    doc["in_stock"] = doc["total_stock"] > 0
    doc["embedding_text"] = generate_product_embedding_text(doc)
    return doc
