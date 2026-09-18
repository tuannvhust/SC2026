"""
src/memory/semantic_rag/ingestion.py
Chịu trách nhiệm chuẩn hóa catalog sản phẩm và chính sách cửa hàng từ data/catalog/catalog.json
thành các documents có cấu trúc kèm metadata và trường `embedding_text` để tạo vector embeddings.
"""

import os
import json
from typing import Dict, Any, List, Tuple


def format_price(v: int) -> str:
    if v is None:
        return "0đ"
    return f"{v:,.0f}đ".replace(",", ".")


def generate_product_embedding_text(p: Dict[str, Any]) -> str:
    """
    Sinh đoạn văn bản tự nhiên giàu ngữ nghĩa tiếng Việt từ thông tin sản phẩm,
    tối ưu cho việc tạo vector embedding cho RAG và Hybrid Search.
    """
    name = p.get("name", "")
    sku = p.get("sku", "")
    brand = p.get("brand", "")
    cat = p.get("category", "")
    
    cat_names = {
        "dien_thoai": "Điện thoại",
        "laptop": "Laptop",
        "phu_kien_dien_tu": "Phụ kiện điện tử"
    }
    cat_vn = cat_names.get(cat, cat)
    
    parts = [f"{cat_vn} {name} (Mã SKU: {sku}) của thương hiệu {brand}."]
    
    # Specs
    specs = p.get("specs", {})
    spec_parts = []
    if "screen_inch" in specs:
        spec_parts.append(f"màn hình {specs['screen_inch']} inch")
    if "battery_mah" in specs:
        spec_parts.append(f"pin {specs['battery_mah']} mAh")
    if "chipset" in specs:
        spec_parts.append(f"vi xử lý chip {specs['chipset']}")
    if "cpu" in specs:
        spec_parts.append(f"CPU {specs['cpu']}")
    if "gpu" in specs:
        spec_parts.append(f"GPU card đồ họa {specs['gpu']}")
    if "camera_mp" in specs:
        spec_parts.append(f"camera {specs['camera_mp']} MP")
    if "os" in specs:
        spec_parts.append(f"hệ điều hành {specs['os']}")
    if "weight_kg" in specs:
        spec_parts.append(f"trọng lượng {specs['weight_kg']} kg")
    if "ports" in specs:
        spec_parts.append(f"cổng kết nối {specs['ports']}")
    if "fan_count" in specs:
        spec_parts.append(f"số quạt tản nhiệt {specs['fan_count']}")
    if "connectivity" in specs:
        spec_parts.append(f"kết nối {specs['connectivity']}")
    if "water_resistance" in specs:
        spec_parts.append(f"chuẩn chống nước {specs['water_resistance']}")
    if "battery_life_hours" in specs:
        spec_parts.append(f"thời lượng pin {specs['battery_life_hours']} giờ")
    if "led" in specs:
        spec_parts.append("có đèn LED" if specs["led"] else "không có LED")
    if "max_laptop_inch" in specs:
        spec_parts.append(f"hỗ trợ laptop tối đa {specs['max_laptop_inch']} inch")
        
    if spec_parts:
        parts.append("Thông số kỹ thuật: " + ", ".join(spec_parts) + ".")
        
    # Variants & Pricing
    variants = p.get("variants", [])
    if variants:
        variant_desc = []
        for v in variants:
            v_info = []
            if v.get("storage_gb"):
                v_info.append(f"bộ nhớ {v['storage_gb']}GB")
            if v.get("ram_gb"):
                v_info.append(f"RAM {v['ram_gb']}GB")
            if v.get("color"):
                v_info.append(f"màu {v['color']}")
            price = format_price(v.get("price_vnd", 0))
            stock = v.get("stock_qty", 0)
            stock_str = f"còn {stock} máy" if stock > 0 else "hết hàng"
            desc_item = " ".join(v_info) if v_info else "Bản tiêu chuẩn"
            variant_desc.append(f"{desc_item} giá {price} ({stock_str})")
        parts.append("Các phiên bản lựa chọn: " + "; ".join(variant_desc) + ".")
        
    # Warranty
    w = p.get("warranty_months")
    if w:
        parts.append(f"Thời gian bảo hành chính hãng: {w} tháng.")
        
    # Installment
    inst = p.get("installment", {})
    if inst.get("supported"):
        rate = inst.get("interest_rate", 0)
        min_m = inst.get("min_months", 3)
        max_m = inst.get("max_months", 12)
        if rate == 0:
            parts.append(f"Hỗ trợ trả góp lãi suất 0% kỳ hạn linh hoạt từ {min_m} đến {max_m} tháng.")
        else:
            parts.append(f"Hỗ trợ trả góp kỳ hạn từ {min_m} đến {max_m} tháng với lãi suất {rate}%.")
    else:
        parts.append("Không áp dụng chính sách trả góp.")
        
    # Trade-in
    trade = p.get("trade_in", {})
    if trade.get("supported"):
        parts.append("Có chương trình thu cũ đổi mới (Trade-in) trợ giá lên đời máy.")
    else:
        parts.append("Không áp dụng chương trình thu cũ đổi mới.")
        
    # Promos
    promos = [pr for pr in p.get("promos", []) if pr.get("active")]
    if promos:
        promo_desc = [f"{pr['description']} (Mã: {pr['promo_code']}, giảm {format_price(pr['discount_vnd'])})" for pr in promos]
        parts.append("Khuyến mãi hiện hành: " + "; ".join(promo_desc) + ".")
        
    return " ".join(parts)


def parse_catalog_file(catalog_file_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Đọc catalog.json và trả về 2 danh sách:
    - products_docs: Các documents sản phẩm kèm trường metadata và embedding_text
    - policies_docs: Các documents chính sách (đổi trả, bảo hành, vận chuyển/COD)
    """
    with open(catalog_file_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
        
    cat_names = {
        "dien_thoai": "Điện thoại",
        "laptop": "Laptop",
        "phu_kien_dien_tu": "Phụ kiện điện tử"
    }
    
    # Chuẩn hóa sản phẩm
    products_docs = []
    for p in data.get("products", []):
        variants = p.get("variants", [])
        prices = [v.get("price_vnd") for v in variants if v.get("price_vnd") is not None]
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0
        total_stock = sum(v.get("stock_qty", 0) for v in variants)
        in_stock = total_stock > 0
        
        inst = p.get("installment", {})
        has_inst = inst.get("supported", False)
        has_inst_0 = has_inst and (inst.get("interest_rate", 1) == 0)
        
        trade = p.get("trade_in", {})
        active_promos = [pr for pr in p.get("promos", []) if pr.get("active", False)]
        
        doc = {
            "_id": p["sku"],
            "sku": p["sku"],
            "name": p["name"],
            "category": p["category"],
            "category_name": cat_names.get(p["category"], p["category"]),
            "brand": p["brand"],
            "min_price": min_price,
            "max_price": max_price,
            "total_stock": total_stock,
            "in_stock": in_stock,
            "installment": {
                **inst,
                "is_zero_percent": has_inst_0
            },
            "trade_in": trade,
            "warranty_months": p.get("warranty_months"),
            "specs": p.get("specs", {}),
            "variants": variants,
            "promos": p.get("promos", []),
            "has_active_promos": len(active_promos) > 0,
            "embedding_text": generate_product_embedding_text(p)
        }
        products_docs.append(doc)
        
    # Chuẩn hóa chính sách
    policies = data.get("policies", {})
    ret_pol = policies.get("return_policy", {})
    ship_pol = policies.get("shipping_policy", {})
    war_pol = policies.get("warranty_policy", {})
    
    policies_docs = [
        {
            "_id": "policy_return",
            "policy_id": "return_policy",
            "title": "Chính sách đổi trả sản phẩm",
            "category": "doi_tra",
            "details": ret_pol,
            "embedding_text": (
                f"Chính sách đổi trả sản phẩm của cửa hàng: Khách hàng được đổi trả trong vòng {ret_pol.get('window_days', 7)} ngày "
                f"đối với trường hợp đổi ý ({ret_pol.get('defect_vs_change_mind', {}).get('change_mind_window_days', 7)} ngày), "
                f"và trong vòng {ret_pol.get('defect_vs_change_mind', {}).get('defective_window_days', 30)} ngày đối với trường hợp máy phát sinh lỗi kỹ thuật do nhà sản xuất. "
                f"Điều kiện đổi trả: {ret_pol.get('conditions', 'còn nguyên hộp, phụ kiện')}. "
                f"Phí vận chuyển đổi trả: Cửa hàng chịu toàn bộ chi phí vận chuyển ({ret_pol.get('who_pays_shipping', 'shop')})."
            )
        },
        {
            "_id": "policy_shipping",
            "policy_id": "shipping_policy",
            "title": "Chính sách giao hàng và thanh toán COD",
            "category": "giao_hang",
            "details": ship_pol,
            "embedding_text": (
                "Chính sách giao hàng và thanh toán khi nhận hàng: "
                "Tại TP.HCM (HCMC), miễn phí giao hàng (0đ), thời gian nhận hàng dự kiến trong 1 ngày. "
                "Tại các tỉnh thành khác trên toàn quốc, phí giao hàng là 30.000đ, thời gian nhận hàng dự kiến 3 ngày. "
                f"Cửa hàng có hỗ trợ hình thức thanh toán khi nhận hàng (ship COD: {ship_pol.get('cod_supported')}), "
                f"áp dụng cho đơn hàng có giá trị tối đa lên đến {format_price(ship_pol.get('cod_max_value_vnd', 15000000))}."
            )
        },
        {
            "_id": "policy_warranty",
            "policy_id": "warranty_policy",
            "title": "Chính sách bảo hành sản phẩm",
            "category": "bao_hanh",
            "details": war_pol,
            "embedding_text": (
                "Chính sách bảo hành sản phẩm chính hãng: "
                "Thời hạn bảo hành tiêu chuẩn theo từng ngành hàng: Điện thoại bảo hành 12 tháng, "
                "Laptop bảo hành 24 tháng, Phụ kiện điện tử bảo hành 6 tháng. "
                "Ngoài ra, cửa hàng có hỗ trợ cung cấp thêm các gói bảo hành mở rộng (bảo hành nâng cao) "
                "cho khách hàng có nhu cầu bảo vệ máy toàn diện."
            )
        }
    ]
    
    return products_docs, policies_docs

