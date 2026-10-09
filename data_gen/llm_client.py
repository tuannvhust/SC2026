from __future__ import annotations

import json
import os
import random
import re
import time

from .config import MODEL


_last_request_at: float | None = None


def _wait_between_requests() -> None:
    global _last_request_at
    interval = max(0.0, float(os.getenv("GEMINI_MIN_INTERVAL_SECONDS", "2.0")))
    if _last_request_at is not None:
        remaining = interval - (time.monotonic() - _last_request_at)
        if remaining > 0:
            time.sleep(remaining)
    _last_request_at = time.monotonic()


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        value = headers.get("retry-after") or headers.get("Retry-After")
        try:
            if value is not None:
                return max(0.0, float(value))
        except (TypeError, ValueError):
            pass
    match = re.search(r"retry(?: after| in)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*s?", str(exc), re.IGNORECASE)
    return float(match.group(1)) if match else None


def _retry_delay(exc: Exception, attempt: int) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return retry_after
    return min(60.0, (2.0 ** attempt) * 2.0 + random.uniform(0.0, 1.5))


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
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) is required unless --dry-run is used")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Install the Gemini SDK with: pip install google-genai") from exc

    client = genai.Client(api_key=api_key)
    last_error = None
    for attempt in range(3):
        try:
            _wait_between_requests()
            response = client.models.generate_content(
                model=MODEL,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=1800,
                    response_mime_type="application/json",
                    seed=seed,
                ),
            )
            text = getattr(response, "text", None)
            if not text:
                raise RuntimeError("Gemini returned an empty response")
            return text.strip()
        except Exception as exc:
            last_error = exc
            if attempt < 2: time.sleep(_retry_delay(exc, attempt))
    raise RuntimeError(f"Gemini request failed after 3 attempts: {last_error}")
