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
    delay = _retry_after_seconds(exc)
    return delay if delay is not None else min(60.0, (2.0 ** attempt) * 2.0 + random.uniform(0.0, 1.5))


def _offline_customer_turns(user: str) -> str:
    data = json.loads(user)
    facts = data.get("facts_established", {})
    details = ", ".join(f"{key}: {value}" for key, value in facts.items())
    turns = [
        f"Alo, em muốn trao đổi về nhu cầu này: {data.get('call_goal', '')}",
        f"Thông tin phía em là {details}." if details else "Em muốn hỏi thêm thông tin trước khi quyết định ạ.",
        "Em cần thông tin chính xác và điều kiện áp dụng giúp em nhé.",
        "Nếu cần thì em sẽ trao đổi thêm rồi phản hồi sau ạ.",
    ]
    return json.dumps(turns, ensure_ascii=False)


def complete(system: str, user: str, *, seed: int, temperature: float, dry_run: bool = False) -> str:
    if dry_run:
        return _offline_customer_turns(user)
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
                    max_output_tokens=1200,
                    response_mime_type="application/json",
                    seed=seed,
                ),
            )
            result = getattr(response, "text", None)
            if not result:
                raise RuntimeError("Gemini returned an empty response")
            return result.strip()
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(_retry_delay(exc, attempt))
    raise RuntimeError(f"Gemini request failed after 3 attempts: {last_error}")
