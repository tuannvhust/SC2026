"""
src/memory/semantic_rag/ingestion.py
Chịu trách nhiệm chuẩn hóa 1 document đọc từ MongoDB Atlas thành document sẵn sàng để embedding và đưa vào Qdrant.
Input: 1 document Mongo (Dict)
Output: Document đã được tính toán metadata và sinh trường `embedding_text` chuẩn tiếng Việt.
"""

from typing import Dict, Any, Optional


def format_price(v: Optional[int]) -> str:
    if v is None:
        return "0đ"
    return f"{v:,.0f}đ".replace(",", ".")


def generate_product_embedding_text(p: Dict[str, Any]) -> str:
    """
    Sinh đoạn văn bản tự nhiên giàu ngữ nghĩa tiếng Việt từ 1 Mongo document sản phẩm.
    """
    name = p.get("name", "")
    sku = p.get("sku") or p.get("_id", "")
    brand = p.get("brand", "")
    cat = p.get("category", "")

    cat_names = {
        "dien_thoai": "Điện thoại",
        "laptop": "Laptop",
        "phu_kien_dien_tu": "Phụ kiện điện tử"
    }
    cat_vn = cat_names.get(cat, cat)

    parts = [f"{cat_vn} {name} (Mã SKU: {sku}) của thương hiệu {brand}."]

    # Thông số kỹ thuật
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

    # Phiên bản & giá bán
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

    # Bảo hành
    w = p.get("warranty_months")
    if w:
        parts.append(f"Thời gian bảo hành chính hãng: {w} tháng.")

    # Trả góp
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

    # Thu cũ đổi mới
    trade = p.get("trade_in", {})
    if trade.get("supported"):
        parts.append("Có chương trình thu cũ đổi mới (Trade-in) trợ giá lên đời máy.")
    else:
        parts.append("Không áp dụng chương trình thu cũ đổi mới.")

    # Khuyến mãi
    promos = [pr for pr in p.get("promos", []) if pr.get("active")]
    if promos:
        promo_desc = [f"{pr['description']} (Mã: {pr['promo_code']}, giảm {format_price(pr.get('discount_vnd', 0))})" for pr in promos]
        parts.append("Khuyến mãi hiện hành: " + "; ".join(promo_desc) + ".")

    return " ".join(parts)


def generate_policy_embedding_text(policy_doc: Dict[str, Any]) -> str:
    """
    Sinh đoạn văn bản tự nhiên từ 1 Mongo document chính sách.
    """
    # Nếu trong Mongo document đã có embedding_text thì ưu tiên dùng
    if policy_doc.get("embedding_text"):
        return policy_doc["embedding_text"]

    pid = policy_doc.get("policy_id") or policy_doc.get("_id", "")
    details = policy_doc.get("details", policy_doc)

    if "return" in pid or "doi_tra" in str(policy_doc.get("category", "")):
        return (
            f"Chính sách đổi trả sản phẩm của cửa hàng: Khách hàng được đổi trả trong vòng {details.get('window_days', 7)} ngày "
            f"đối với trường hợp đổi ý, và trong vòng {details.get('defect_vs_change_mind', {}).get('defective_window_days', 30)} ngày "
            f"đối với trường hợp máy phát sinh lỗi kỹ thuật do nhà sản xuất. "
            f"Điều kiện đổi trả: {details.get('conditions', 'còn nguyên hộp, phụ kiện')}. "
            f"Phí vận chuyển đổi trả: Cửa hàng chịu toàn bộ chi phí vận chuyển ({details.get('who_pays_shipping', 'shop')})."
        )
    elif "shipping" in pid or "giao_hang" in str(policy_doc.get("category", "")):
        return (
            "Chính sách giao hàng và thanh toán khi nhận hàng: "
            "Tại TP.HCM (HCMC), miễn phí giao hàng (0đ), thời gian nhận hàng dự kiến trong 1 ngày. "
            "Tại các tỉnh thành khác trên toàn quốc, phí giao hàng là 30.000đ, thời gian nhận hàng dự kiến 3 ngày. "
            f"Cửa hàng có hỗ trợ hình thức thanh toán khi nhận hàng (ship COD: {details.get('cod_supported')}), "
            f"áp dụng cho đơn hàng có giá trị tối đa lên đến {format_price(details.get('cod_max_value_vnd', 15000000))}."
        )
    elif "warranty" in pid or "bao_hanh" in str(policy_doc.get("category", "")):
        return (
            "Chính sách bảo hành sản phẩm chính hãng: "
            "Thời hạn bảo hành tiêu chuẩn theo từng ngành hàng: Điện thoại bảo hành 12 tháng, "
            "Laptop bảo hành 24 tháng, Phụ kiện điện tử bảo hành 6 tháng. "
            "Ngoài ra, cửa hàng có hỗ trợ cung cấp thêm các gói bảo hành mở rộng (bảo hành nâng cao) "
            "cho khách hàng có nhu cầu bảo vệ máy toàn diện."
        )

    return str(details)


def ingest_product_document(mongo_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chuẩn hóa 1 Mongo document sản phẩm:
    - Tính toán lại min_price, max_price, total_stock, in_stock (nếu chưa có)
    - Sinh embedding_text chuẩn tiếng Việt
    """
    doc = dict(mongo_doc)
    doc_id = doc.get("_id") or doc.get("sku")
    doc["_id"] = str(doc_id)
    doc["sku"] = doc.get("sku", str(doc_id))

    variants = doc.get("variants", [])
    prices = [v.get("price_vnd") for v in variants if v.get("price_vnd") is not None]

    if "min_price" not in doc or doc["min_price"] is None:
        doc["min_price"] = min(prices) if prices else 0
    if "max_price" not in doc or doc["max_price"] is None:
        doc["max_price"] = max(prices) if prices else 0

    total_stock = sum(v.get("stock_qty", 0) for v in variants)
    doc["total_stock"] = total_stock
    doc["in_stock"] = total_stock > 0

    # Sinh hoặc cập nhật embedding_text
    doc["embedding_text"] = generate_product_embedding_text(doc)
    return doc


def ingest_policy_document(mongo_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chuẩn hóa 1 Mongo document chính sách và sinh embedding_text.
    """
    doc = dict(mongo_doc)
    doc_id = doc.get("_id") or doc.get("policy_id")
    doc["_id"] = str(doc_id)
    doc["embedding_text"] = generate_policy_embedding_text(doc)
    return doc
