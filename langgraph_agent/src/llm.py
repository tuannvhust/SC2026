import json
import os
import re
from typing import Any, Dict

from .state import CallState
from .tools import CATALOG

_FAKE_BAD_PRICE_ONCE = False  # cờ kiểm thử: buộc stand-in cố tình bịa giá sai 1 lần để test guardrail


def get_model() -> str:
    return os.getenv("HARNESS_MODEL", "claude-sonnet-4-6")


def use_fake_llm() -> bool:
    return not os.getenv("ANTHROPIC_API_KEY")


def real_llm_json(system: str, user: str) -> Dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=get_model(),
        max_tokens=800,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def real_llm_text(system: str, user: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=get_model(),
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def fmt_vnd(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def fake_plan(state: CallState) -> Dict[str, Any]:
    """Bộ lập kế hoạch (stand-in) theo luật để test graph offline. KHÔNG dùng để báo cáo metric kết quả."""
    global _FAKE_BAD_PRICE_ONCE
    msgs = state.get("messages", [])
    last_user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "").lower()
    profile = state.get("profile", {})
    results = state.get("tool_results", [])
    first_turn = not any(m["role"] == "assistant" for m in msgs)
    facts: Dict[str, Any] = {}

    m = re.search(r"(\d+)\s*(?:m2|m²)", last_user)
    if m:
        facts["room_area_m2"] = int(m.group(1))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:tr|triệu)", last_user)
    if m:
        facts["budget_vnd"] = int(float(m.group(1).replace(",", ".")) * 1_000_000)
    if "hỏi chồng" in last_user or "hỏi vợ" in last_user:
        facts["blocker"] = "cần hỏi người nhà"

    # 1) Đã có kết quả tool trong lượt này -> trả lời dựa trên kết quả đó
    if results:
        last = results[-1]
        if last["tool"] == "order_create":
            r = last["result"]
            return {
                "action": "answer",
                "facts": {"blocker": None},
                "draft_response": f"Dạ em đã tạo đơn {r['order_id']} giá {fmt_vnd(r['price_vnd'])}đ cho anh/chị rồi ạ.",
            }
        items = last["result"]
        if not items:
            return {"action": "cannot_answer", "facts": facts}
        it = items[0]
        promo = f" Hiện có ưu đãi {it['active_promos'][0]['desc']}." if it["active_promos"] else ""
        prefix = ""
        if first_turn and state.get("call_brief"):
            prefix = state["call_brief"] + " "
        text = f"{prefix}Dạ {it['name']} hiện giá {fmt_vnd(it['price_vnd'])}đ.{promo}"
        if _FAKE_BAD_PRICE_ONCE and state.get("retry_count", 0) == 0:
            text = f"Dạ {it['name']} hiện giá {fmt_vnd(it['price_vnd'] - 300_000)}đ ạ."  # cố tình hallucinate giá
        facts.update({"product_advised": it["sku"], "price_quoted_vnd": it["price_vnd"]})
        return {"action": "answer", "draft_response": text, "facts": facts}

    # 2) Khách cũ ở lượt đầu -> gọi tool xác minh lại sản phẩm đã tư vấn
    if first_turn and profile.get("product_advised") and not results:
        return {
            "action": "call_tool",
            "facts": facts,
            "tool_calls": [{"name": "catalog_search", "args": {"query": profile["product_advised"]}}],
        }
    # 3) Khách chốt mua và đã biết sản phẩm -> tạo đơn hàng
    if any(k in last_user for k in ["lấy", "chốt", "đặt"]) and profile.get("product_advised"):
        return {
            "action": "call_tool",
            "facts": facts,
            "tool_calls": [
                {
                    "name": "order_create",
                    "args": {
                        "customer_id": state["customer_id"],
                        "sku": profile["product_advised"],
                        "price_vnd": CATALOG[profile["product_advised"]]["price_vnd"],
                    },
                }
            ],
        }
    # 4) Khách hỏi giá hoặc thông tin máy lọc
    if any(k in last_user for k in ["giá", "máy lọc", "lọc không khí", "bao nhiêu"]):
        return {
            "action": "call_tool",
            "facts": facts,
            "tool_calls": [{"name": "catalog_search", "args": {"query": last_user}}],
        }
    # 5) Khách đưa ra lý do cản trở (blocker) hoặc phản hồi xã giao
    if facts:
        return {
            "action": "answer",
            "facts": facts,
            "draft_response": "Dạ vâng ạ, em ghi nhận rồi. Anh/chị cứ trao đổi thêm, cần gì em hỗ trợ tiếp ạ.",
        }
    return {"action": "cannot_answer", "facts": facts}
