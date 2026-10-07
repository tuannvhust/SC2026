from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.graph.state import AgentState
from src.memory.profile.mem0_store import get_profile_store
from src.memory.working.sqlite_store import SQLiteMemoryStore
from src.tools.tool_repository import crm_get_customer


# ---------------------------------------------------------------------------
# Call Brief schema
# ---------------------------------------------------------------------------

class LastSession(BaseModel):
    session_id: str
    date: str
    channel: str
    summary: str
    outcome: str


class CallBrief(BaseModel):
    customer_phone: str
    customer_name: Optional[str] = None
    honorific: Optional[str] = None

    is_returning: bool
    n_previous_sessions: int

    last_session: Optional[LastSession] = None

    profile_facts: Dict[str, Any] = Field(default_factory=dict)
    products_advised: List[Dict[str, Any]] = Field(default_factory=list)
    orders: List[Dict[str, Any]] = Field(default_factory=list)
    open_blockers: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    must_not_ask: List[str] = Field(default_factory=list)
    stale_warnings: List[str] = Field(default_factory=list)

    suggested_opening: str
    suggested_next_action: str

    generated_at: str
    latency_ms: int

    precomputed_parts: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

TEENCODE_MAP = {
    "sp": "sản phẩm",
    "spm": "sản phẩm",
    "k": "không",
    "ko": "không",
    "kh": "khách hàng",
    "mk": "mình",
    "mik": "mình",
    "dc": "được",
    "đc": "được",
    "vs": "với",
    "bn": "bao nhiêu",
    "ib": "inbox",
    "roi": "rồi",
    "r": "rồi",
    "a": "ạ",
    "e": "em",
    "cj": "chị",
}


def _get_last_message_text(state: AgentState) -> str:
    messages = state.get("messages", [])

    if not messages:
        return ""

    content = messages[-1].content

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))

        return " ".join(parts)

    return str(content)


def _clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_teencode(text: str) -> str:
    return " ".join(TEENCODE_MAP.get(token.lower(), token) for token in text.split())


def _normalize_money(text: str) -> str:
    def replace_million(match: re.Match) -> str:
        value = match.group(1).replace(",", ".")
        parts = value.split(".")

        if len(parts) == 2 and len(parts[1]) <= 3:
            million = int(parts[0])
            thousand = int(parts[1].ljust(3, "0"))
            amount = million * 1_000_000 + thousand
            return f"{amount:,}".replace(",", ".")

        amount = int(float(value) * 1_000_000)
        return f"{amount:,}".replace(",", ".")

    def replace_thousand(match: re.Match) -> str:
        value = match.group(1).replace(",", ".")
        amount = int(float(value) * 1_000)
        return f"{amount:,}".replace(",", ".")

    text = re.sub(r"\b(\d+(?:[.,]\d+)?)\s*(?:tr|triệu)\b", replace_million, text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\d+(?:[.,]\d+)?)\s*(?:k|nghìn)\b", replace_thousand, text, flags=re.IGNORECASE)

    return text


def _normalize_input(text: str) -> str:
    text = _clean_whitespace(text)
    text = _normalize_teencode(text)
    text = _normalize_money(text)
    return text


def _extract_phone(text: str) -> Optional[str]:
    match = re.search(r"\b0\d{9}\b", text)
    return match.group(0) if match else None


# ---------------------------------------------------------------------------
# Input nodes
# ---------------------------------------------------------------------------

def input_guardrail_node(state: AgentState) -> Dict[str, Any]:
    """Validate the incoming customer message."""
    text = _get_last_message_text(state).strip()
    now = datetime.now().isoformat()
    session_context = {
        "session_id": state.get("session_id") or str(uuid.uuid4()),
        "session_started_at": state.get("session_started_at") or now,
        "turn_id": str(uuid.uuid4()),
    }

    if not text:
        return {"input_valid": False, **session_context}

    suspicious_patterns = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"reveal\s+(your|the)\s+system\s+prompt",
        r"show\s+(me\s+)?the\s+system\s+prompt",
        r"bypass\s+(the\s+)?guardrail",
        r"\bjailbreak\b",
    ]

    if any(re.search(pattern, text, re.IGNORECASE) for pattern in suspicious_patterns):
        return {"input_valid": False, **session_context}

    meaningful_text = re.sub(r"[\W_]+", "", text)

    if len(meaningful_text) < 2:
        return {"input_valid": False, **session_context}

    return {"input_valid": True, **session_context}


def normalize_input_node(state: AgentState) -> Dict[str, Any]:
    """
    Normalize the current message.

    The normalized text is kept temporarily inside customer_info so the
    state schema stays small.
    """

    text = _get_last_message_text(state)
    normalized = _normalize_input(text)

    customer_info = dict(state.get("customer_info") or {})

    customer_info["_input_text"] = normalized
    return {"customer_info": customer_info}


def resolve_identity_node(state: AgentState) -> Dict[str, Any]:
    """Resolve the current customer through the CRM tool."""

    context = dict(state.get("customer_info") or {})

    text = context.get("_input_text", "")

    phone = context.get("phone") or _extract_phone(text)
    zalo_id = context.get("zalo_id")
    fb_id = context.get("fb_id")

    result = crm_get_customer.invoke({"phone": phone, "zalo_id": zalo_id, "fb_id": fb_id})

    customer_info = dict(result)

    customer_info["phone"] = result.get("phone") or phone

    customer_info["_input_text"] = text
    return {
        "customer_id": result.get("customer_id"),
        "customer_info": customer_info,
    }


# ---------------------------------------------------------------------------
# Call Brief helpers
# ---------------------------------------------------------------------------

def _get_last_session(sessions: List[Dict[str, Any]]) -> Optional[LastSession]:
    if not sessions:
        return None

    latest = max(sessions, key=lambda item: item.get("date", ""))

    return LastSession(
        session_id=str(latest.get("session_id", "")),
        date=str(latest.get("date", "")),
        channel=str(latest.get("channel", "other")),
        summary=str(latest.get("summary", "")),
        outcome=str(latest.get("outcome", "khac")),
    )


def _build_must_not_ask(
    profile_facts: Dict[str, Any],
    products_advised: List[Dict[str, Any]],
) -> List[str]:
    slots = [key for key, value in profile_facts.items() if value is not None]

    if products_advised:
        slots.append("product_advised")

    return sorted(set(slots))


def _build_suggested_opening(
    customer_name: Optional[str],
    honorific: Optional[str],
    last_session: Optional[LastSession],
    products_advised: List[Dict[str, Any]],
    open_blockers: List[str],
) -> str:
    title = honorific or "anh/chị"

    if customer_name:
        greeting = f"Dạ chào {title} {customer_name} ạ."
    else:
        greeting = f"Dạ chào {title} ạ."

    if not last_session:
        return f"{greeting} Em hỗ trợ mình vấn đề gì hôm nay ạ?"

    if not products_advised:
        return f"{greeting} Em tiếp tục hỗ trợ mình từ lần trao đổi trước nhé ạ?"

    product = products_advised[-1]
    sku = product.get("sku")

    if open_blockers:
        blocker = open_blockers[0]

        return (
            f"{greeting} Hôm trước bên em có tư vấn mẫu "
            f"{sku or 'sản phẩm mình quan tâm'}. Mình còn băn khoăn về {blocker} đúng không ạ?"
        )

    return (
        f"{greeting} Hôm trước bên em có tư vấn mẫu "
        f"{sku or 'sản phẩm mình quan tâm'}. Em hỗ trợ mình tiếp nhé ạ?"
    )


# ---------------------------------------------------------------------------
# Call Brief node
# ---------------------------------------------------------------------------

def build_call_brief_node(state: AgentState) -> Dict[str, Any]:
    """Build the structured CallBrief for the planner."""

    started_at = time.perf_counter()

    customer_info = state.get("customer_info") or {}

    customer_id = state.get("customer_id")

    sessions = customer_info.get("sessions", [])
    orders = customer_info.get("orders", [])

    profile_facts = (
        get_profile_store().get_profile_facts(customer_id)
        if customer_id
        else {}
    )
    episodes = (
        SQLiteMemoryStore().get_recent_episodes(customer_id)
        if customer_id
        else []
    )
    episode_sessions = [
        {
            "session_id": episode["session_id"],
            "date": episode["ended_at"],
            "channel": "other",
            "summary": episode.get("summary", ""),
            "outcome": episode.get("outcome", "khac"),
        }
        for episode in episodes
    ]
    sessions = [*sessions, *episode_sessions]
    products_advised = [
        product
        for episode in reversed(episodes)
        for product in episode.get("products_advised", [])
    ]
    latest_episode = episodes[0] if episodes else {}
    open_blockers = latest_episode.get(
        "open_blockers",
        [],
    )
    open_questions = latest_episode.get(
        "open_questions",
        [],
    )
    last_session = _get_last_session(sessions)

    stale_warnings = []

    for product in products_advised:
        if product.get("promo_still_active") is False:
            stale_warnings.append(
                f"Promotion {product.get('promo_code') or 'previously quoted'} "
                "may no longer be active."
            )

    must_not_ask = _build_must_not_ask(profile_facts, products_advised)
    suggested_opening = _build_suggested_opening(
        customer_info.get("name"),
        customer_info.get("honorific"),
        last_session,
        products_advised,
        open_blockers,
    )

    if open_blockers:
        suggested_next_action = f"Address the open blocker: {open_blockers[0]}"
    elif products_advised:
        suggested_next_action = "Continue the previous discussion without repeating known information."
    else:
        suggested_next_action = "Understand the customer's current need."

    latency_ms = int((time.perf_counter() - started_at) * 1000)

    brief = CallBrief(
        customer_phone=customer_info.get("phone") or "",
        customer_name=customer_info.get("name"),
        honorific=customer_info.get("honorific"),
        is_returning=bool(sessions),
        n_previous_sessions=len(sessions),
        last_session=last_session,
        profile_facts=profile_facts,
        products_advised=products_advised,
        orders=orders,
        open_blockers=open_blockers,
        open_questions=open_questions,
        must_not_ask=must_not_ask,
        stale_warnings=stale_warnings,
        suggested_opening=suggested_opening,
        suggested_next_action=suggested_next_action,
        generated_at=datetime.now().isoformat(),
        latency_ms=latency_ms,
        precomputed_parts=[
            "customer_identity",
            "session_count",
            "last_session",
            "profile_facts",
            "products_advised",
            "open_blockers",
            "must_not_ask",
        ],
    )

    return {"call_brief": brief.model_dump(mode="json")}