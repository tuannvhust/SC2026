from __future__ import annotations

import json
import os
import random
import time
from typing import Any

from .config import MODEL


def _offline_dialogue(user: str, seed: int) -> str:
    data = json.loads(user)
    facts = data["fact_pack"]
    call = data["call"]
    product = facts.get("products", [{}])[0]
    catalog = (product.get("catalog", {}).get("items") or [{}])[0]
    quote = product.get("quote", {})
    name = catalog.get("name", "sản phẩm")
    price = quote.get("final_price_vnd")
    price_text = f"{price:,}".replace(",", ".") + "đ" if isinstance(price, int) else "em kiểm tra lại giá giúp anh/chị ạ"
    customer_facts = facts.get("customer_facts", {})
    area = customer_facts.get("room_area_m2")
    outcome = call.get("expected_outcome")
    customer = facts.get("customer", {})
    honorific = customer.get("honorific") or "anh/chị"
    turns = [
        {"role": "customer", "text": f"Alo, {honorific} cho hỏi {name} giá bao nhiêu ạ?"},
        {"role": "agent", "text": f"Dạ em kiểm tra theo ngày gọi, {name} hiện có giá {price_text} ạ."},
        {"role": "customer", "text": f"Phòng nhà {honorific} khoảng {area}m2, sản phẩm có phù hợp không?" if area else "Sản phẩm này dùng có ổn không em?"},
        {"role": "agent", "text": "Dạ em sẽ tư vấn theo thông tin sản phẩm trong hệ thống ạ."},
        {"role": "customer", "text": "Nếu có chương trình phù hợp thì em nói rõ điều kiện giúp anh/chị nhé."},
        {"role": "agent", "text": "Dạ chương trình và điều kiện áp dụng sẽ được kiểm tra theo ngày, sản phẩm và hồ sơ khách hàng ạ."},
    ]
    if outcome == "chot_don":
        turns += [{"role": "customer", "text": "Được rồi, em lên đơn giúp anh/chị nhé."}, {"role": "agent", "text": "Dạ em sẽ xác nhận lại thông tin đơn trước khi tạo ạ."}]
    elif outcome == "hen_goi_lai":
        turns += [{"role": "customer", "text": "Để anh/chị trao đổi thêm với gia đình rồi gọi lại em nhé."}, {"role": "agent", "text": "Dạ vâng, em ghi nhận và hỗ trợ mình khi gọi lại ạ."}]
    elif outcome == "chuyen_may":
        turns += [{"role": "customer", "text": "Câu này em có chắc thông tin không?"}, {"role": "agent", "text": "Dạ nội dung này ngoài phạm vi tư vấn của em, em xin phép chuyển bộ phận phù hợp ạ."}]
    else:
        turns += [{"role": "customer", "text": "Vậy em kiểm tra giúp anh/chị nhé."}, {"role": "agent", "text": "Dạ hiện em chưa có thông tin chắc chắn để trả lời ạ."}]
    return json.dumps(turns, ensure_ascii=False)


def complete(system: str, user: str, *, seed: int, temperature: float, dry_run: bool = False) -> str:
    if dry_run:
        return _offline_dialogue(user, seed)
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is required unless --dry-run is used")
    import anthropic
    last_error = None
    for attempt in range(3):
        try:
            response = anthropic.Anthropic().messages.create(
                model=MODEL, max_tokens=1800, temperature=temperature,
                system=system, messages=[{"role": "user", "content": user}],
            )
            return "".join(getattr(block, "text", "") for block in response.content).strip()
        except Exception as exc:
            last_error = exc
            if attempt < 2: time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM request failed after 3 attempts: {last_error}")
