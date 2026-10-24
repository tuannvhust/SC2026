"""Payload rules for product documents indexed in Qdrant."""

from typing import Any, Dict

PRODUCT_PAYLOAD_FIELDS = frozenset(
    {
        "_id",
        "chunk_id",
        "chunk_index",
        "sku",
        "name",
        "title",
        "heading",
        "category",
        "brand",
        "attributes",
        "embedding_text",
        "source_path",
        "access_level",
        "is_active",
        "variants",
    }
)
STATIC_VARIANT_FIELDS = ("variant_sku", "size", "color")


def sanitize_product_payload(document: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only approved static product fields and variant descriptors."""
    payload = {
        key: document[key]
        for key in PRODUCT_PAYLOAD_FIELDS - {"variants"}
        if key in document
    }
    variants = document.get("variants")
    if isinstance(variants, list):
        payload["variants"] = [
            {
                key: variant[key]
                for key in STATIC_VARIANT_FIELDS
                if key in variant
            }
            for variant in variants
            if isinstance(variant, dict)
        ]
    return payload
