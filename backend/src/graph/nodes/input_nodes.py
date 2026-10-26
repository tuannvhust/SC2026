from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from jsonschema import Draft202012Validator, FormatChecker

from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage

from src.graph.state import AgentState
from src.memory.profile.profile_store import get_profile_store
from src.memory.working.postgres_store import get_postgres_memory_store
from src.tools.tool_repository import (
    _is_valid_phone,
    _normalize_phone,
    crm_create_customer_if_absent,
    crm_get_customer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Call Brief schema
# ---------------------------------------------------------------------------

CallBriefOutcome = Literal[
    "hen_goi_lai",
    "chot_don",
    "tu_choi",
    "chuyen_may",
    "khac",
]


class LastSession(BaseModel):
    session_id: str
    date: str
    channel: str
    summary: str
    outcome: CallBriefOutcome

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
    recent_sessions: List[LastSession] = Field(default_factory=list)

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
    memory_status: str = "empty"
    memory_sources: Dict[str, Any] = Field(default_factory=dict)


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

@lru_cache(maxsize=1)
def _get_call_brief_validator() -> Draft202012Validator:
    """Load and cache the canonical CallBrief JSON Schema."""
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "schemas"
        / "call_brief.schema.json"
    )

    with schema_path.open("r", encoding="utf-8") as file:
        schema = json.load(file)

    Draft202012Validator.check_schema(schema)

    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )


def _validate_call_brief_schema(
    brief: Dict[str, Any],
) -> None:
    """Raise an actionable error if the generated brief violates its schema."""
    validator = _get_call_brief_validator()

    errors = sorted(
        validator.iter_errors(brief),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )

    if not errors:
        return

    details = "; ".join(
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in errors[:10]
    )

    raise ValueError(
        f"Generated CallBrief does not match "
        f"data/schemas/call_brief.schema.json: {details}"
    )

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
    """Extract and normalize a Vietnamese phone number from free text.

    Supports:
    - 0xxxxxxxxx
    - +84xxxxxxxxx or +84 xxxxxxxxx
    - Numbers separated by spaces, dots, or hyphens (e.g. 0912 345 678, 0912.345.678)
    """
    if not text:
        return None
    # Find sequence starting with +84, 84, or 0 followed by 9 digits with optional separators
    pattern = re.compile(r"(?:(?:\+84|84|0)[.\s-]?)(\d[.\s-]?){8}\d")
    match = pattern.search(text)
    if match:
        digits = re.sub(r"\D", "", match.group(0))
        if digits.startswith("84") and len(digits) > 9:
            digits = "0" + digits[2:]
        if len(digits) == 10 and digits.startswith("0"):
            return digits
    return None


# Max times we ask for name+phone before falling back to guest mode.
MAX_IDENTITY_ATTEMPTS = 3

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
_NAME_PATTERNS = [
    r"(?:m(?:i|ì)nh|t(?:o|ô)i|tớ|to|em|anh|ch(?:i|ị))\s+t(?:e|ê)n\s+(?:l(?:a|à)\s+)?([^\W\d_]+(?:\s+[^\W\d_]+){0,3})",
    r"(?:t(?:e|ê)n\s+(?:m(?:i|ì)nh|t(?:o|ô)i|em|anh|ch(?:i|ị))\s+(?:l(?:a|à)\s+)?)([^\W\d_]+(?:\s+[^\W\d_]+){0,3})",
    r"(?:t(?:o|ô)i|m(?:i|ì)nh|em|anh|ch(?:i|ị))\s+l(?:a|à)\s+([^\W\d_]+(?:\s+[^\W\d_]+){0,3})",
    r"(?:t(?:e|ê)n\s*(?:l(?:a|à)|:)?\s*)([^\W\d_]+(?:\s+[^\W\d_]+){0,3})",
]


def _clean_name_candidate(candidate: str) -> Optional[str]:
    name = _clean_whitespace(candidate or "").strip(" .,;:!?-")
    if not name or len(name) > 40:
        return None
    # Avoid capturing phone numbers or sentences as names.
    if re.search(r"\d", name):
        return None
    tokens = name.split()
    stopwords = {
        "ạ", "nhé", "nha", "dạ", "vâng", "ừ", "ok", "oke",
        "số", "điện", "thoại", "sdt", "phone", "tên", "la", "là",
    }
    valid_tokens = [tok for tok in tokens if tok.lower() not in stopwords]
    if not valid_tokens or len(valid_tokens) > 4:
        return None
    return " ".join(valid_tokens).title()


def _extract_name(text: str) -> Optional[str]:
    cleaned = _clean_whitespace(text or "")
    if not cleaned:
        return None

    # Strip out any phone number before analyzing name
    phone_p = re.compile(r"(?:(?:\+84|84|0)[.\s-]?)(\d[.\s-]?){8}\d")
    m = phone_p.search(cleaned)
    text_without_phone = cleaned
    if m:
        text_without_phone = cleaned[:m.start()] + " " + cleaned[m.end():]

    for pattern in _NAME_PATTERNS:
        match = re.search(pattern, text_without_phone, flags=re.IGNORECASE)
        if match:
            name = _clean_name_candidate(match.group(1))
            if name:
                return name

    # Fallback: check if user provided direct name format (e.g. "Kim Trúc, sđt 0912..." or "Kim Trúc")
    # Clean marker words like 'sdt', 'so dien thoai', 'phone'
    stripped = re.sub(
        r"(?i)\b(s(?:đ|d)t|s(?:ố|o)\s*(?:đ|d)i(?:ệ|e)n\s*tho(?:ạ|a)i|phone|d(?:ạ|a)|v(?:â|a)ng)\b",
        " ",
        text_without_phone,
    )
    stripped = _clean_whitespace(stripped).strip(" ,.;:-_")
    candidate = _clean_name_candidate(stripped)
    if candidate:
        # Extra guard: avoid common phrases like "tư vấn giúp mình", "xem máy lọc"
        not_names = {"tư vấn", "tu van", "xem", "mua", "hoi", "hỏi", "giá", "gia", "máy lọc", "may loc"}
        if not any(nn in candidate.lower() for nn in not_names):
            return candidate

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

    customer_info["_call_brief_started_perf"] = time.perf_counter()
    return {"customer_info": customer_info}


def resolve_identity_node(state: AgentState) -> Dict[str, Any]:
    """Resolve the current customer through the CRM tool.

    Handles three cases:
      A. customer_id already present in state — reuse if valid, never overwrite
         a resolved identity with unverified data.
      B. No phone available — ask user to supply one (needs_input).
      C. Phone provided — normalize, validate, call crm_get_customer, then
         act on resolved / not_found / ambiguous / invalid_input / system_error.
    """

    # ---- Case A — customer_id already present in state ----
    existing_customer_id = state.get("customer_id")
    if existing_customer_id:
        context = dict(state.get("customer_info") or {})
        context["_input_text"] = context.get("_input_text", "") or ""
        return {
            "customer_id": existing_customer_id,
            "customer_info": context,
            "needs_identity": False,
            "identity_status": "resolved",
            "identity_attempts": 0,
            "missing_identity_fields": [],
            "pending_need": state.get("pending_need"),
        }

    # ---- Prepare context and extract phone ----
    context = dict(state.get("customer_info") or {})
    text = context.get("_input_text", "") or ""
    raw_text = _get_last_message_text(state) or text

    # Fallback: phone/name may live in a previous brief if customer_info was
    # rebuilt (checkpointer path) — never lose verified identity across turns.
        # Recover historical context, but prefer a name explicitly provided
    # in the current message when the previous identity needs clarification.
    brief_fallback = dict(state.get("call_brief") or {})
    missing_fields = set(state.get("missing_identity_fields") or [])

    extracted_name = _extract_name(raw_text or text)

    if extracted_name and (
        "name" in missing_fields
        or not _real_name(context.get("name"))
    ):
        context["name"] = extracted_name

    if (
        not _real_name(context.get("name"))
        and _real_name(brief_fallback.get("customer_name"))
    ):
        context["name"] = brief_fallback["customer_name"]

    phone = (
        context.get("phone")
        or _extract_phone(text)
        or _extract_phone(raw_text)
        or brief_fallback.get("customer_phone")
    )

    # Kênh Zalo/Facebook đã có ID: tra CRM trước khi hỏi lại số điện thoại.
    channel_zalo = str(context.get("zalo_id") or "").strip() or None
    channel_fb = str(context.get("fb_id") or "").strip() or None
    if not phone and (channel_zalo or channel_fb):
        channel_result = crm_get_customer.invoke(
            {
                "phone": None,
                "name": None,
                "zalo_id": channel_zalo,
                "fb_id": channel_fb,
            }
        )
        if channel_result.get("error"):
            return {
                "customer_id": None,
                "customer_info": context,
                "needs_identity": True,
                "identity_status": "system_error",
                "identity_attempts": int(state.get("identity_attempts") or 0) + 1,
                "missing_identity_fields": ["phone"],
                "pending_need": state.get("pending_need"),
            }
        if (
            channel_result.get("found")
            and channel_result.get("customer_id")
            and not channel_result.get("ambiguous")
            and not channel_result.get("identity_conflict")
        ):
            if channel_zalo:
                context["zalo_id"] = channel_zalo
            if channel_fb:
                context["fb_id"] = channel_fb
            matched_phone = _normalize_phone(channel_result.get("phone"))
            matched_name = _real_name(channel_result.get("name"))
            if matched_name:
                context["name"] = matched_name
            if matched_phone and _is_valid_phone(matched_phone):
                phone = matched_phone
                context["phone"] = matched_phone
            else:
                customer_id = channel_result["customer_id"]
                session_id = state.get("session_id")
                if customer_id and session_id:
                    get_postgres_memory_store().update_session_customer_id(
                        session_id, customer_id
                    )
                return {
                    "customer_id": customer_id,
                    "customer_info": {**context, **channel_result, "customer_id": customer_id},
                    "needs_identity": False,
                    "identity_status": "resolved",
                    "identity_attempts": 0,
                    "missing_identity_fields": [],
                    "pending_need": state.get("pending_need"),
                }

    # ---- Case B — no phone available ----
    if not phone:
        pending_need = state.get("pending_need")
        if not pending_need:
            pending_need = _clean_whitespace(raw_text or text)[:500] or None
        return {
            "customer_id": None,
            "customer_info": context,
            "needs_identity": True,
            "identity_status": "needs_input",
            "identity_attempts": int(state.get("identity_attempts") or 0),
            "missing_identity_fields": ["phone", "name"],
            "pending_need": pending_need,
        }

    # ---- Case C — phone present: normalize & validate ----
    normalized_phone = _normalize_phone(phone)
    if not _is_valid_phone(normalized_phone):
        return {
            "customer_id": None,
            "customer_info": {**context, "phone": phone},
            "needs_identity": True,
            "identity_status": "invalid_input",
            "identity_attempts": int(state.get("identity_attempts") or 0) + 1,
            "missing_identity_fields": ["phone"],
            "pending_need": state.get("pending_need"),
        }
    context["phone"] = normalized_phone

    # ---- Call CRM repository (real query on Supabase) ----
    result = crm_get_customer.invoke(
    {
        "phone": normalized_phone,
        "name": _real_name(context.get("name")),
        "zalo_id": None,
        "fb_id": None,
    }
    )

    # System error (not not_found) — distinguish clearly.
    # Increment identity_attempts so repeated system errors eventually exhaust
    # the attempt budget and fall through to guest mode instead of looping.
    if result.get("error"):
        current_missing = list(state.get("missing_identity_fields") or ["phone"])
        if not current_missing:
            current_missing = ["phone"]
        return {
            "customer_id": None,
            "customer_info": {**context, "phone": normalized_phone},
            "needs_identity": True,
            "identity_status": "system_error",
            "identity_attempts": int(state.get("identity_attempts") or 0) + 1,
            "missing_identity_fields": current_missing,
            "pending_need": state.get("pending_need"),
        }

    # Ambiguous / conflicting result — do not auto-pick a customer
        # Ambiguous / conflicting result — never assign a customer automatically.
    if result.get("ambiguous") or result.get("identity_conflict"):
        identity_status = (
            "identity_conflict"
            if result.get("identity_conflict")
            else "ambiguous"
        )

        return {
            "customer_id": None,
            "customer_info": {
                **context,
                "phone": normalized_phone,
            },
            "needs_identity": True,
            "identity_status": identity_status,
            "identity_attempts": (
                int(state.get("identity_attempts") or 0) + 1
            ),
            "missing_identity_fields": ["name"],
            "pending_need": state.get("pending_need"),
        }

    # Determine customer_id from CRM result
    crm_customer_id = result["customer_id"] if result.get("found") else None

    # ---- Case G — CRM lookup returns not_found ----
    if not crm_customer_id:
        has_provided_name = _real_name(context.get("name")) is not None
        if not has_provided_name:
            # Phone is valid but name is missing: ask only for the missing name
            return {
                "customer_id": None,
                "customer_info": {**context, "phone": normalized_phone},
                "needs_identity": True,
                "identity_status": "not_found",
                "identity_attempts": int(state.get("identity_attempts") or 0) + 1,
                "missing_identity_fields": ["name"],
                "pending_need": state.get("pending_need"),
            }

        # Valid phone + real, non-generic customer name: register customer
        channel = context.get("channel") or "web_chat"
        reg_result = crm_create_customer_if_absent(
            phone=normalized_phone,
            name=context["name"],
            honorific=context.get("honorific"),
            source=f"application_chat_{channel}",
        )

        outcome = reg_result.get("outcome")
        if outcome in {"created", "reused"}:
            customer_id = reg_result["customer_id"]
            session_id = state.get("session_id")
            if customer_id and session_id:
                try:
                    get_postgres_memory_store().update_session_customer_id(
                        session_id, customer_id
                    )
                except Exception as link_err:
                    logger.error(
                        "Failed to associate session %s with registered customer %s: %s",
                        session_id, customer_id, link_err, exc_info=True
                    )
                    # Surface linking failure accurately while preserving registered identity
                    return {
                        "customer_id": customer_id,
                        "customer_info": {
                            **context,
                            "customer_id": customer_id,
                            "phone": normalized_phone,
                            "name": reg_result.get("name") or context["name"],
                            "honorific": reg_result.get("honorific") or context.get("honorific"),
                        },
                        "needs_identity": True,
                        "identity_status": "system_error",
                        "identity_attempts": int(state.get("identity_attempts") or 0) + 1,
                        "missing_identity_fields": [],
                        "pending_need": state.get("pending_need"),
                    }

            updated_context = {
                **context,
                "customer_id": customer_id,
                "phone": normalized_phone,
                "name": reg_result.get("name") or context["name"],
                "honorific": reg_result.get("honorific") or context.get("honorific"),
            }

            pending_need = state.get("pending_need")
            latest_text = _clean_whitespace(raw_text or text)
            if latest_text and pending_need and latest_text not in pending_need:
                stripped = re.sub(r"\b0\d{9}\b", "", latest_text).strip(" ,.;:-")
                if stripped and stripped not in pending_need:
                    pending_need = f"{pending_need} | {stripped[:500]}"[:1000]
            elif latest_text and not pending_need:
                pending_need = latest_text[:500]

            return {
                "customer_id": customer_id,
                "customer_info": updated_context,
                "needs_identity": False,
                "identity_status": "resolved",
                "identity_attempts": 0,
                "missing_identity_fields": [],
                "pending_need": pending_need,
            }
        elif outcome == "ambiguous":
            return {
                "customer_id": None,
                "customer_info": {**context, "phone": normalized_phone},
                "needs_identity": True,
                "identity_status": "ambiguous",
                "identity_attempts": int(state.get("identity_attempts") or 0) + 1,
                "missing_identity_fields": ["name"],
                "pending_need": state.get("pending_need"),
            }
        else:
            # Registration failure (invalid_input or system_error)
            status = "system_error" if outcome == "system_error" else "invalid_input"
            return {
                "customer_id": None,
                "customer_info": {**context, "phone": normalized_phone},
                "needs_identity": True,
                "identity_status": status,
                "identity_attempts": int(state.get("identity_attempts") or 0) + 1,
                "missing_identity_fields": ["phone", "name"] if status == "invalid_input" else [],
                "pending_need": state.get("pending_need"),
            }


    # ---- Exactly one valid customer found ----
    customer_id = crm_customer_id
    session_id = state.get("session_id")
    if customer_id and session_id:
        get_postgres_memory_store().update_session_customer_id(
            session_id, customer_id
        )

    customer_info = {**context, **result}
    customer_info["phone"] = normalized_phone
    crm_name = _real_name(result.get("name"))
    if crm_name:
        customer_info["name"] = crm_name
    elif context.get("name"):
        customer_info["name"] = context.get("name")

    # needs_identity: require both customer_id AND a real name
    has_name = _real_name(customer_info.get("name")) is not None
    missing_fields = []
    if not has_name:
        missing_fields.append("name")
    needs_identity = bool(missing_fields)

    pending_need = state.get("pending_need")
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
        "identity_status": "resolved" if not needs_identity else "needs_input",
        "identity_attempts": 0 if not needs_identity else int(state.get("identity_attempts") or 0) + 1,
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
    identity_status = state.get("identity_status")
    if identity_status in {"ambiguous", "identity_conflict"}:
        question = (
            "Dạ em chưa xác định được chính xác hồ sơ theo số điện thoại "
            "này ạ. Mình xác nhận giúp em họ tên đầy đủ đã đăng ký với shop "
            "để em tra cứu đúng thông tin nhé ạ?"
        )
    elif missing == ["name"]:
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

def _get_last_session(sessions: List[Dict[str, Any]],) -> Optional[LastSession]:
    if not sessions:
        return None

    latest = max(
        sessions,
        key=lambda item: str(item.get("date") or ""),
    )

    return LastSession(
        session_id=str(latest.get("session_id", "")),
        date=str(latest.get("date", "")),
        channel=str(latest.get("channel") or "other"),
        summary=str(latest.get("summary") or ""),
        outcome=str(latest.get("outcome") or "other")
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

    started_at = customer_info.get("_call_brief_started_perf")
    if not isinstance(started_at, (int, float)):
        started_at = time.perf_counter()

    customer_id = state.get("customer_id")
    session_id = state.get("session_id")

    sessions = customer_info.get("sessions", [])
    orders = customer_info.get("orders", [])

    memory_errors = []
    working_store = None
    working_store_error = None
    try:
        working_store = get_postgres_memory_store()
    except Exception as error:
        working_store_error = error
        logger.warning(
            "Call Brief memory-store initialization failed: %s",
            type(error).__name__,
            exc_info=True,
        )
        if session_id:
            memory_errors.append("working_events")
        if customer_id:
            memory_errors.append("episodic_memory")

    try:
        session_events = (
            working_store.get_session_events(
                session_id, customer_id=customer_id, limit=20
            )
            if session_id and working_store
            else []
        )
    except Exception as error:
        logger.warning(
            "Call Brief working-memory read failed for session %s: %s",
            session_id,
            type(error).__name__,
            exc_info=True,
        )
        session_events = []
        memory_errors.append("working_events")
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

    try:
        profile_store = get_profile_store()
        profile_facts_with_provenance = (
            profile_store.get_profile_facts_with_provenance(customer_id)
            if customer_id
            else {}
        )
        profile_facts = {
            key: fact["value"]
            for key, fact in profile_facts_with_provenance.items()
        }
    except Exception as error:
        logger.warning(
            "Call Brief profile-memory read failed for customer %s: %s",
            customer_id,
            type(error).__name__,
            exc_info=True,
        )
        profile_facts_with_provenance = {}
        profile_facts = {}
        if customer_id:
            memory_errors.append("profile_facts")
    try:
        episodes = (
            working_store.get_recent_episodes(customer_id, limit=5)
            if customer_id and working_store
            else []
        )
    except Exception as error:
        logger.warning(
            "Call Brief episodic-memory read failed for customer %s: %s",
            customer_id,
            type(error).__name__,
            exc_info=True,
        )
        episodes = []
        if customer_id:
            memory_errors.append("episodic_memory")

    def _as_text_list(value):
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    episode_sessions = [
        {
            "session_id": episode["session_id"],
            "date": (
                episode["ended_at"].isoformat()
                if hasattr(episode.get("ended_at"), "isoformat")
                else str(episode.get("ended_at") or "")
            ),
            "channel": str(episode.get("channel") or "other"),
            "summary": (
                "Historical, not verified as current: "
                + str(episode.get("summary") or "")
            ),
            "outcome": episode.get("outcome", "khac"),
        }
        for episode in episodes
        if episode.get("session_id")
    ]
    sessions = [*sessions, *episode_sessions]

    def _historical_product_summaries(items):
        summaries = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            summary = {
                key: item[key]
                for key in ("sku", "name")
                if isinstance(item.get(key), str) and item[key].strip()
            }
            if summary:
                summaries.append(summary)
        return summaries

    products_advised = [
        product
        for episode in reversed(episodes)
        for product in _historical_product_summaries(
            episode.get("products_advised")
        )
    ]
    latest_episode = episodes[0] if episodes else {}
    open_blockers = _as_text_list(
        latest_open_brief.get("open_blockers")
        or latest_episode.get("open_blockers")
    )
    open_questions = _as_text_list(
        latest_open_brief.get("open_questions")
        or latest_episode.get("open_questions")
    )
    if latest_open_brief.get("products_advised"):
        products_advised.extend(
            _historical_product_summaries(latest_open_brief["products_advised"])
        )
    last_session = _get_last_session(sessions)

    stale_warnings = []
    if episodes or products_advised:
        stale_warnings.append(
            "Historical prices, stock, promotions, and policies must be "
            "re-verified before advising."
        )
    if open_blockers or open_questions:
        stale_warnings.append(
            "Previously recorded blockers and questions need confirmation "
            "before treating them as current."
        )

    must_not_ask = _build_must_not_ask(profile_facts, products_advised, customer_info)
    suggested_opening = _build_suggested_opening(
        customer_info.get("name"),
        customer_info.get("honorific"),
        last_session,
        products_advised,
        open_blockers,
    )

    next_actions = _as_text_list(latest_episode.get("next_actions"))
    if open_blockers:
        suggested_next_action = (
            f"Confirm whether this previous blocker remains: {open_blockers[0]}"
        )
    elif open_questions:
        suggested_next_action = (
            f"Confirm whether this previous question is still open: "
            f"{open_questions[0]}"
        )
    elif next_actions:
        suggested_next_action = next_actions[0]
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

    memory_has_data = bool(profile_facts or episodes or current_session_history)
    if memory_errors:
        memory_status = "partial" if memory_has_data else "error"
    else:
        memory_status = "loaded" if memory_has_data else "empty"
    memory_sources = {
        "profile_facts": {
            key: {
                "session_id": fact.get("source_session_id"),
                "updated_at": (
                    fact["updated_at"].isoformat()
                    if hasattr(fact.get("updated_at"), "isoformat")
                    else fact.get("updated_at")
                ),
            }
            for key, fact in profile_facts_with_provenance.items()
        },
        "episodes": [episode["session_id"] for episode in episodes if episode.get("session_id")],
        "working_events": [
            event["event_id"] for event in open_session_events if event.get("event_id")
        ],
    }

    brief = CallBrief(
        customer_id=customer_id,
        customer_phone=customer_info.get("phone") or "",
        customer_name=resolved_name,
        honorific=customer_info.get("honorific"),
        session_id=session_id,
        is_returning=bool(sessions),
        n_previous_sessions=len(sessions),
        last_session=last_session,
        recent_sessions=[
            LastSession(
                session_id=str(session["session_id"]),
                date=str(session["date"]),
                channel=str(session.get("channel") or "other"),
                summary=str(session.get("summary") or ""),
                outcome=str(session.get("outcome") or "other"),
            )
            for session in episode_sessions
        ],
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
        generated_at=datetime.now(timezone.utc).isoformat(),
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
        memory_status=memory_status,
        memory_sources=memory_sources,
    )

    brief_dict = brief.model_dump(mode="json")
    _validate_call_brief_schema(brief_dict)
    if session_id:
        if working_store is None:
            raise RuntimeError(
                "Cannot persist Call Brief because memory storage is unavailable."
            ) from working_store_error
        brief_dict["call_brief_revision"] = working_store.save_call_brief(
            session_id=session_id,
            customer_id=customer_id,
            call_brief=brief_dict,
        )
        brief_dict["call_brief_updated_at"] = (datetime.now(timezone.utc).isoformat())
    _validate_call_brief_schema(brief_dict)

    if customer_id and resolved_name:
        identity_state = {
            "needs_identity": False,
            "identity_status": "resolved",
            "identity_attempts": 0,
            "missing_identity_fields": [],
        }
    elif customer_id and not resolved_name:
        # Phone resolved to a customer_id but name still missing.
        identity_state = {
            "needs_identity": True,
            "identity_status": "needs_input",
            "missing_identity_fields": ["name"],
        }
    else:
        # No customer_id — propagate current needs_identity from state so
        # routing functions always see a consistent value (never stale).
        current_needs = state.get("needs_identity", False)
        current_status = state.get("identity_status") or "needs_input"
        identity_state = {
            "needs_identity": current_needs,
            "identity_status": current_status,
        }
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

    return {"call_brief": brief_dict, **identity_state}
