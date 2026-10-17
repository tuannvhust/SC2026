from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage

from src.graph.state import AgentState
from src.memory.profile.profile_store import get_profile_store
from src.memory.working.postgres_store import get_postgres_memory_store
from src.tools.tool_repository import crm_get_customer

logger = logging.getLogger(__name__)


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
    customer_id: Optional[str] = None
    customer_phone: str
    customer_name: Optional[str] = None
    honorific: Optional[str] = None
    # Current session, used as provenance for memory.write tool calls.
    session_id: Optional[str] = None

    is_returning: bool
    n_previous_sessions: int

    last_session: Optional[LastSession] = None

    # Original request that triggered identity collection (Turn 1 need).
    current_need: Optional[str] = None
    # Key buying constraints extracted for the current turn.
    constraints: Dict[str, Any] = Field(default_factory=dict)
    # Compact per-tool summary for the current turn (no raw JSON dumps).
    tool_summary: List[Dict[str, Any]] = Field(default_factory=list)

    profile_facts: Dict[str, Any] = Field(default_factory=dict)
    products_advised: List[Dict[str, Any]] = Field(default_factory=list)
    orders: List[Dict[str, Any]] = Field(default_factory=list)
    open_blockers: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    current_session_history: List[str] = Field(default_factory=list)
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
    match = re.search(r"\b0\d{9}\b", text or "")
    return match.group(0) if match else None


# Max times we ask for name+phone before falling back to guest mode.
MAX_IDENTITY_ATTEMPTS = 2

_IDENTITY_QUESTION = (
    "Dạ em chưa nhận diện được thông tin của mình ạ. "
    "Mình cho em xin tên và số điện thoại để em hỗ trợ chính xác hơn nhé ạ?"
)

# Generic CRM stub names that must NOT count as a known customer name.
_GENERIC_CUSTOMER_NAMES = {"khách hàng", "khach hang"}


def _real_name(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in _GENERIC_CUSTOMER_NAMES:
        return None
    return cleaned


# Common Vietnamese lead-ins before a name, e.g. "mình tên Lan", "tôi là Minh".
# Patterns accept both accented and unaccented spellings.
_NAME_PATTERNS = [
    r"(?:m[iì]nh|t[ôo]i|tớ|to|em|anh|ch[ịi])\s+t[êe]n\s+(?:l[àa]\s+)?([^\W\d_]+(?:\s+[^\W\d_]+){0,3})",
    r"(?:t[êe]n\s+(?:m[iì]nh|t[ôo]i|em|anh|ch[ịi])\s+(?:l[àa]\s+)?)([^\W\d_]+(?:\s+[^\W\d_]+){0,3})",
    r"(?:t[ôo]i|m[iì]nh|em|anh|ch[ịi])\s+l[àa]\s+([^\W\d_]+(?:\s+[^\W\d_]+){0,3})",
]


def _clean_name_candidate(candidate: str) -> Optional[str]:
    name = _clean_whitespace(candidate or "").strip(" .,;:!?-")
    if not name or len(name) > 40:
        return None
    # Avoid capturing phone numbers or sentences as names.
    if re.search(r"\d", name):
        return None
    tokens = name.split()
    if len(tokens) > 4:
        return None
    stopwords = {
        "ạ", "nhé", "nha", "dạ", "vâng", "ừ", "ok", "oke",
        "số", "điện", "thoại", "sdt", "phone", "tên",
    }
    if all(token.lower() in stopwords for token in tokens):
        return None
    return name.title()


def _extract_name(text: str) -> Optional[str]:
    cleaned = _clean_whitespace(text or "")
    if not cleaned:
        return None
    for pattern in _NAME_PATTERNS:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            name = _clean_name_candidate(match.group(1))
            if name:
                return name
    return None


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
        "turn_id": state.get("turn_id") or str(uuid.uuid4()),
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
    """Resolve the current customer through the CRM tool.

    When no identifier is available, collect name + phone from the reply
    text first so ``build_call_brief`` has enough data in the next turn.
    """

    context = dict(state.get("customer_info") or {})

    text = context.get("_input_text", "") or ""
    # Parse identity from the raw last message: teencode normalization maps
    # "e" -> "em" and would corrupt guest names, so prefer raw text here.
    raw_text = _get_last_message_text(state) or text

    # Fallback: phone/name may live in a previous brief if customer_info was
    # rebuilt (checkpointer path) — never lose verified identity across turns.
    brief_fallback = dict(state.get("call_brief") or {})
    if not context.get("name") and brief_fallback.get("customer_name"):
        context["name"] = brief_fallback["customer_name"]
    previous_name = _real_name(context.get("name"))
    phone = (
        context.get("phone")
        or _extract_phone(text)
        or _extract_phone(raw_text)
        or brief_fallback.get("customer_phone")
    )
    parsed_name = _extract_name(text) or _extract_name(raw_text)
    name = previous_name or parsed_name
    if phone:
        context["phone"] = phone
    if name and not previous_name:
        # Keep guest-provided names temporarily for the next call brief.
        # A self-declared name alone never identifies an existing customer.
        context["name"] = name
    elif previous_name:
        context["name"] = previous_name
    zalo_id = context.get("zalo_id")
    fb_id = context.get("fb_id")

    # Only a phone (or existing channel identifiers) may look up CRM.
    # Never create/synthesize a customer record from a self-declared name.
    result = crm_get_customer.invoke({"phone": phone, "zalo_id": zalo_id, "fb_id": fb_id})

    customer_info = {**context, **result}

    customer_info["phone"] = result.get("phone") or phone
    crm_name = _real_name(result.get("name"))
    if crm_name:
        customer_info["name"] = crm_name
    elif name:
        customer_info["name"] = name
    elif previous_name:
        customer_info["name"] = previous_name
    else:
        customer_info.pop("name", None)
    customer_info["channel"] = context.get("channel") or result.get("channel")
    customer_info["_input_text"] = text
    customer_id = state.get("customer_id") or result.get("customer_id")
    session_id = state.get("session_id")
    if customer_id and session_id:
        get_postgres_memory_store().update_session_customer_id(
            session_id, customer_id
        )

    attempts = int(state.get("identity_attempts") or 0)
    # NOTE: per current product decision, zalo/fb ids alone do NOT count as
    # identified. Require BOTH a resolved customer_id (via phone lookup) AND
    # a verified/real name before clearing the flag.
    has_phone = bool(re.fullmatch(r"0\d{9}", str(customer_info.get("phone") or "")))
    has_name = _real_name(customer_info.get("name")) is not None
    missing_fields = [
        field
        for field, present in (("phone", has_phone), ("name", has_name))
        if not present
    ]
    needs_identity = (not customer_id) or bool(missing_fields)
    pending_need = state.get("pending_need")
    if needs_identity and not pending_need:
        # Keep the original Turn-1 ask so the sale need survives identity turns.
        first_text = _clean_whitespace(raw_text or text)
        if first_text:
            pending_need = first_text[:500]
    if not needs_identity:
        attempts = 0
        missing_fields = []
        # Identity complete: keep the original Turn-1 need; append latest only
        # if it adds new sale content beyond name/phone.
        latest_text = _clean_whitespace(raw_text or text)
        if latest_text and pending_need and latest_text not in pending_need:
            stripped = re.sub(r"\b0\d{9}\b", "", latest_text).strip(" ,.;:-")
            if stripped and stripped not in pending_need:
                pending_need = f"{pending_need} | {stripped[:500]}"[:1000]
        elif latest_text and not pending_need:
            pending_need = latest_text[:500]

    return {
        "customer_id": customer_id,
        "customer_info": customer_info,
        "needs_identity": needs_identity,
        "identity_attempts": attempts,
        "missing_identity_fields": missing_fields,
        "pending_need": pending_need,
    }


def request_identity_node(state: AgentState) -> Dict[str, Any]:
    """Pause the turn and ask for the missing name/phone slots.

    The graph routes to ``persist_turn`` right after this node, so the
    customer reply arrives as a new turn and ``resolve_identity`` runs again
    with the provided contact info before ``build_call_brief``.
    """

    attempts = int(state.get("identity_attempts") or 0) + 1
    customer_info = dict(state.get("customer_info") or {})
    missing = list(state.get("missing_identity_fields") or [])
    if not missing:
        has_phone = bool(
            re.fullmatch(r"0\d{9}", str(customer_info.get("phone") or ""))
        )
        has_name = _real_name(customer_info.get("name")) is not None
        if not has_phone:
            missing.append("phone")
        if not has_name:
            missing.append("name")
    if missing == ["name"]:
        question = (
            "Dạ em đã lưu số điện thoại rồi ạ, mình cho em xin thêm họ tên "
            "để em hỗ trợ chính xác hơn nhé ạ? Mình không cần gửi lại số đâu ạ."
        )
    elif missing == ["phone"]:
        question = (
            "Dạ em đã lưu họ tên rồi ạ, mình cho em xin thêm số điện thoại "
            "để em tra thông tin chính xác hơn nhé ạ?"
        )
    else:
        question = _IDENTITY_QUESTION

    pending_need = state.get("pending_need") or _clean_whitespace(
        customer_info.get("_input_text", "") or ""
    )
    if pending_need:
        pending_need = pending_need[:500]

    return {
        "messages": [AIMessage(content=question)],
        "customer_info": customer_info,
        "needs_identity": True,
        "identity_attempts": attempts,
        "missing_identity_fields": missing or ["phone", "name"],
        "pending_need": pending_need,
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
    customer_info: Optional[Dict[str, Any]] = None,
) -> List[str]:
    slots = [key for key, value in profile_facts.items() if value is not None]

    if products_advised:
        slots.append("product_advised")

    # Do not re-ask for contact slots already collected during identity flow.
    info = customer_info or {}
    if re.fullmatch(r"0\d{9}", str(info.get("phone") or "")):
        slots.append("phone")
    if _real_name(info.get("name")) is not None:
        slots.append("name")

    return sorted(set(slots))


def _mask_phone(phone: Optional[str]) -> str:
    digits = str(phone or "")
    if not re.fullmatch(r"0\d{9}", digits):
        return "none"
    return f"{digits[:3]}***{digits[-4:]}"


def _extract_constraints(text: str) -> Dict[str, Any]:
    """Extract lightweight buying constraints from the current/pending need."""
    cleaned = _clean_whitespace(text or "")
    if not cleaned:
        return {}
    constraints: Dict[str, Any] = {}
    area = re.search(r"(\d+(?:[.,]\d+)?)\s*(m2|m²|m\^2|mét vuông)", cleaned, re.IGNORECASE)
    area_value: Optional[float] = None
    if area:
        try:
            area_value = float(area.group(1).replace(",", "."))
            constraints["room_area_m2"] = area_value
        except ValueError:
            area_value = None
    budget = _normalize_money(cleaned)
    amounts = []
    for match in re.finditer(r"(\d[\d.,]*)\s*(triệu|tr|tỷ|ty|nghìn|nghin|k|đ|vnd|đồng)?", budget, re.IGNORECASE):
        raw_value, unit = match.group(1), (match.group(2) or "").lower()
        try:
            number = float(raw_value.replace(".", "").replace(",", ""))
        except ValueError:
            continue
        # Skip bare area numbers like "30m2" without money markers.
        if not unit and area_value is not None and abs(number - area_value) < 0.001:
            continue
        multiplier = 1
        if unit in ("tỷ", "ty"):
            multiplier = 1_000_000_000
        elif unit in ("triệu", "tr"):
            multiplier = 1_000_000
        elif unit in ("nghìn", "nghin", "k"):
            multiplier = 1_000
        elif unit in ("đ", "vnd", "đồng", ""):
            # Only accept bare numbers >= 100k as VND to avoid area/SKU noise.
            if number < 100_000:
                continue
        amounts.append(int(number * multiplier))
    if amounts:
        constraints["budget_hint_vnd"] = max(amounts)
    lowered = cleaned.lower()
    keywords = ["airpure", "máy lọc", "may loc", "máy lạnh", "điều hòa", "dieu hoa"]
    interested = sorted({key for key in keywords if key in lowered})
    if interested:
        constraints["interested_keywords"] = interested
    sample_match = re.search(r"mau so (\d+)", lowered)
    if sample_match:
        constraints["sample_no"] = int(sample_match.group(1))
    return constraints


def _map_sample_to_sku(sample_no: int) -> Optional[Dict[str, Any]]:
    """Resolve 'mẫu số N' to the Nth product in the project catalog (1-based)."""
    if not sample_no or sample_no < 1:
        return None
    try:
        catalog_path = (
            Path(__file__).resolve().parents[3] / "data" / "catalog" / "products.json"
        )
        with catalog_path.open("r", encoding="utf-8") as handle:
            products = json.load(handle).get("products", [])
    except (OSError, ValueError, AttributeError):
        return None
    if sample_no > len(products):
        return None
    product = products[sample_no - 1]
    return {"sku": product.get("sku"), "name": product.get("name")}


def _summarize_current_tools(messages: List[Any]) -> List[Dict[str, Any]]:
    """Compact tool summary for the current turn only (no raw JSON dumps)."""
    from langchain_core.messages import ToolMessage as _ToolMessage

    summary: List[Dict[str, Any]] = []
    for message in messages or []:
        if not isinstance(message, _ToolMessage):
            continue
        try:
            payload = json.loads(message.content) if isinstance(message.content, str) else {}
        except (ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {"value": str(payload)[:300]}
        item: Dict[str, Any] = {"tool": message.name, "tool_call_id": message.tool_call_id}
        for key in ("sku", "final_price_vnd", "in_stock", "status", "ticket_id", "callback_id"):
            if payload.get(key) is not None:
                item[key] = payload[key]
        if isinstance(payload.get("items"), list) and payload["items"]:
            first = payload["items"][0] if isinstance(payload["items"][0], dict) else {}
            item["top_item"] = {k: first.get(k) for k in ("sku", "name") if first.get(k)}
            item["n_items"] = len(payload["items"])
        summary.append(item)
    return summary[-8:]


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
    """Build the structured CallBrief for the planner.

    Inputs: ``customer_id``/``customer_info`` (identity), Postgres session
    events + recent episodes + profile facts (memory), and the current turn
    text (need/constraints). Output is stored at ``state["call_brief"]`` as a
    compact dict — never a raw copy of ``state["messages"]``.
    """

    started_at = time.perf_counter()

    customer_info = state.get("customer_info") or {}

    customer_id = state.get("customer_id")
    session_id = state.get("session_id")

    sessions = customer_info.get("sessions", [])
    orders = customer_info.get("orders", [])

    session_events = (
        get_postgres_memory_store().get_session_events(session_id)
        if session_id
        else []
    )
    open_session_events = [
        event
        for event in session_events
        if not event.get("payload", {}).get("status", {}).get("session_ended")
    ]
    current_session_history = []
    for event in open_session_events:
        for message in event.get("payload", {}).get("messages", []):
            if not isinstance(message, dict):
                continue
            data = message.get("data", {})
            content = data.get("content", "") if isinstance(data, dict) else ""
            if isinstance(content, str) and content.strip():
                current_session_history.append(
                    f"{message.get('type', 'message')}: {content.strip()}"
                )
    current_session_history = current_session_history[-20:]
    latest_open_brief = (
        open_session_events[-1].get("payload", {}).get("call_brief", {})
        if open_session_events
        else {}
    )

    profile_facts = (
        get_profile_store().get_profile_facts(customer_id)
        if customer_id
        else {}
    )
    episodes = (
        get_postgres_memory_store().get_recent_episodes(customer_id)
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
    open_blockers = latest_open_brief.get("open_blockers") or latest_episode.get(
        "open_blockers", []
    )
    open_questions = latest_open_brief.get("open_questions") or latest_episode.get(
        "open_questions", []
    )
    if latest_open_brief.get("products_advised"):
        products_advised.extend(latest_open_brief["products_advised"])
    last_session = _get_last_session(sessions)

    stale_warnings = []

    for product in products_advised:
        if product.get("promo_still_active") is False:
            stale_warnings.append(
                f"Promotion {product.get('promo_code') or 'previously quoted'} "
                "may no longer be active."
            )

    must_not_ask = _build_must_not_ask(profile_facts, products_advised, customer_info)
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

    # Verified name priority: profile facts > trusted CRM name > guest-parsed.
    profile_name = _real_name(profile_facts.get("name")) if isinstance(profile_facts, dict) else None
    resolved_name = (
        profile_name
        or _real_name(customer_info.get("name"))
        or _real_name(latest_open_brief.get("customer_name"))
    )
    current_need = (
        state.get("pending_need")
        or _clean_whitespace(customer_info.get("_input_text", "") or "")
        or _clean_whitespace(_get_last_message_text(state))
    )[:500] or None
    constraints = _extract_constraints(
        f"{current_need or ''} {_clean_whitespace(customer_info.get('_input_text', '') or '')}"
    )
    if constraints.get("sample_no"):
        interested_product = _map_sample_to_sku(int(constraints["sample_no"]))
        if interested_product:
            constraints["interested_sku"] = interested_product["sku"]
            constraints["interested_product_name"] = interested_product["name"]
    tool_summary = _summarize_current_tools(state.get("messages", []))

    brief = CallBrief(
        customer_id=customer_id,
        customer_phone=customer_info.get("phone") or "",
        customer_name=resolved_name,
        honorific=customer_info.get("honorific"),
        session_id=session_id,
        is_returning=bool(sessions),
        n_previous_sessions=len(sessions),
        last_session=last_session,
        current_need=current_need,
        constraints=constraints,
        tool_summary=tool_summary,
        profile_facts=profile_facts,
        products_advised=products_advised,
        orders=orders,
        open_blockers=open_blockers,
        open_questions=open_questions,
        current_session_history=current_session_history,
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

    brief_dict = brief.model_dump(mode="json")
    # Safe debug log: structure + masked phone only, never full PII.
    logger.debug(
        "call_brief built fields=%s has_name=%s has_phone=%s need_len=%s "
        "tools=%s latency_ms=%s phone=%s",
        sorted(brief_dict.keys()),
        bool(brief_dict.get("customer_name")),
        bool(brief_dict.get("customer_phone")),
        len(brief_dict.get("current_need") or ""),
        [item.get("tool") for item in brief_dict.get("tool_summary") or []],
        latency_ms,
        _mask_phone(brief_dict.get("customer_phone")),
    )

    return {"call_brief": brief_dict}
