"""Correlated execution tracing shared by the API graph runner and the CLI.

One format for both entry points:

    [GRAPH][run=abc123] START ...
    [GRAPH][run=abc123][node=input_guardrail] END status=success duration_ms=12 summary=...
    [GRAPH][run=abc123] END status=success duration_ms=2140

Node START/END pairs and durations come from LangGraph ``stream_mode="debug"``
events (``type=task`` / ``type=task_result``); only what the execution trace
actually emitted is logged. Summaries are sanitized (no PII, no secrets,
no raw prompts/payloads) and length-capped.

Verbosity is controlled with ``GRAPH_TRACE_LEVEL``:
``silent`` (off) | ``warn`` (only failures) | ``info`` (default) | ``debug``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field

LOGGER = logging.getLogger("src.graph.trace")
if not LOGGER.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.propagate = False
LOGGER.setLevel(logging.DEBUG)

_LEVELS = {"silent": 99, "off": 99, "warn": 30, "warning": 30, "info": 20, "debug": 10}

_PHONE_RE = re.compile(r"(?<!\d)(0\d{9})(?!\d)")
_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|token|secret|password|authorization)\b\s*[:=]\s*\S+"
)
_ERROR_CODE_RE = re.compile(r"['\"]error_code['\"]?\s*[:=]\s*['\"]?([\w-]+)")
_EVAL_TRACE_LOCK = Lock()


class _TraceQuestion(BaseModel):
    slot: str
    type: str = Field(pattern=r"^(open|confirm)$")
    text: str


class _TraceClaim(BaseModel):
    field: str
    value: Any
    text: Optional[str] = None


class _TraceToolCall(BaseModel):
    name: str
    args: Dict[str, Any]
    result: Any = None


class _TraceLatency(BaseModel):
    ttft_ms: int = Field(ge=0)
    total_ms: int = Field(ge=0)
    ttfa_ms: Optional[int] = Field(default=None, ge=0)


class _EvalTraceLine(BaseModel):
    run_id: str
    config: str = Field(pattern=r"^(baseline_no_memory|full)$")
    scenario_id: str
    call: str = Field(pattern=r"^call_[123]$")
    turn: int = Field(ge=1)
    customer_text: str
    agent_text: str
    questions: list[_TraceQuestion]
    claims: list[_TraceClaim]
    tool_calls: list[_TraceToolCall]
    latency: _TraceLatency
    facts_used: list[str] = Field(default_factory=list)
    call_brief_latency_ms: Optional[int] = Field(default=None, ge=0)
    memory_writes: list[Dict[str, Any]] = Field(default_factory=list)
    customer_input_mode: Optional[str] = Field(
        default=None, pattern=r"^(clean|asr_transcript|chat_teencode)$"
    )


def append_eval_trace_line(record: Dict[str, Any], path: str | Path) -> None:
    """Validate one BTC trace row and append it as UTF-8 JSONL atomically.

    This is intentionally called only by evaluation callers that provide real
    run/scenario metadata and a measured TTFT; API traffic has neither.
    """
    validated = _EvalTraceLine.model_validate(record)
    serialized = validated.model_dump_json(exclude_none=True)
    with _EVAL_TRACE_LOCK:
        with Path(path).open("a", encoding="utf-8", newline="\n") as trace_file:
            trace_file.write(serialized + "\n")


def build_eval_trace_record(
    *, state: Dict[str, Any], run_id: str, total_ms: int, context: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a schema-shaped row from one completed graph turn.

    The caller must provide scenario/config/call/turn and measured TTFT. Claims
    and questions are deliberately extracted only from the emitted assistant
    text; richer team extractors can replace these fields in the eval harness.
    """
    messages = state.get("messages") or []
    last_user_index = next(
        (i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)),
        None,
    )
    turn_messages = messages[last_user_index:] if last_user_index is not None else []
    customer_message = messages[last_user_index] if last_user_index is not None else None
    customer_text = _message_content(customer_message)
    assistant_text = next(
        (
            _message_content(message)
            for message in reversed(turn_messages)
            if isinstance(message, AIMessage) and _message_content(message).strip()
        ),
        "",
    )

    questions = []
    for question in re.findall(r"[^?？]*[?？]", assistant_text):
        question = question.strip()
        if question:
            is_confirm = bool(
                re.search(r"đúng không|phải không|vẫn .* chứ|đã .* chưa", question, re.I)
            )
            questions.append(
                {"slot": "unspecified", "type": "confirm" if is_confirm else "open", "text": question}
            )

    claims = []
    for match in re.finditer(
        r"(?<!\d)(\d{1,3}(?:[., ]\d{3})+|\d+)\s*(?:đ|vnđ|vnd|đồng)",
        assistant_text,
        re.I,
    ):
        amount = int(re.sub(r"\D", "", match.group(1)))
        claims.append({"field": "price_vnd", "value": amount, "text": match.group(0)})

    tool_calls = []
    result_by_id = {
        message.tool_call_id: message
        for message in turn_messages
        if isinstance(message, ToolMessage)
    }
    for message in turn_messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            call_id = call.get("id")
            result = result_by_id.get(call_id) if isinstance(call_id, str) else None
            tool_calls.append(
                {
                    "name": call.get("name") or "unknown",
                    "args": _trace_safe(call.get("args") or {}),
                    "result": _trace_safe(_message_content(result)) if result else None,
                }
            )
    tool_calls.extend(_trace_safe(state.get("trace_tool_calls") or []))

    facts_used = []
    profile_facts = (state.get("call_brief") or {}).get("profile_facts") or {}
    for key, fact in profile_facts.items() if isinstance(profile_facts, dict) else []:
        value = fact.get("value") if isinstance(fact, dict) else fact
        if value is not None and str(value).strip() and str(value).casefold() in assistant_text.casefold():
            facts_used.append(str(key))

    record = {
        "run_id": run_id,
        "config": context["config"],
        "scenario_id": context["scenario_id"],
        "call": context["call"],
        "turn": context["turn"],
        "customer_text": _mask_trace_text(customer_text),
        "agent_text": _mask_trace_text(assistant_text),
        "questions": [
            {**item, "text": _mask_trace_text(item["text"])} for item in questions
        ],
        "claims": claims,
        "tool_calls": tool_calls,
        "latency": {"ttft_ms": context["ttft_ms"], "total_ms": total_ms},
        "facts_used": facts_used,
        "call_brief_latency_ms": context.get("call_brief_latency_ms"),
        "memory_writes": _trace_safe(state.get("memory_writes") or []),
    }
    if context.get("customer_input_mode") is not None:
        record["customer_input_mode"] = context["customer_input_mode"]
    return _EvalTraceLine.model_validate(record).model_dump(exclude_none=True)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "") if message is not None else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(part["text"]) for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return str(content or "")


def _mask_trace_text(value: str) -> str:
    value = _PHONE_RE.sub("[đã ẩn SĐT]", value)
    return re.sub(r"(?<!\d)\d{9,14}(?!\d)", "[đã ẩn thông tin nhạy cảm]", value)


def _trace_safe(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {str(k): _trace_safe(v, str(k).lower()) for k, v in value.items()}
    if isinstance(value, list):
        return [_trace_safe(item, key) for item in value]
    if isinstance(value, str):
        if any(term in key for term in ("phone", "sdt", "citizen", "cccd", "account", "stk")):
            return "[đã ẩn]"
        return _mask_trace_text(value)
    return value


def sanitize(text: Any, limit: int = 200) -> str:
    """Collapse whitespace, mask phones/secrets, and cap length."""
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = json.dumps(text, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(text)
    text = _SECRET_RE.sub(r"\1=***", text)
    text = _PHONE_RE.sub("0***", text)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit] + "...(cut)"
    return text


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]


def _epoch(value: Any) -> float:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return time.time()


class GraphTrace:
    """Correlation-id scoped logger for one graph run."""

    def __init__(
        self,
        run_id: str,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        level: Optional[str] = None,
    ) -> None:
        self.run_id = run_id
        self.session_id = session_id
        self.turn_id = turn_id
        self._min = _LEVELS.get(
            (level or os.getenv("GRAPH_TRACE_LEVEL", "info")).strip().lower(), 20
        )
        self._open: Dict[Any, float] = {}
        self._t0 = time.perf_counter()

    def _emit(self, message: str, level: int = logging.INFO) -> None:
        if self._min >= 99:
            return
        if self._min > logging.INFO and level < logging.WARNING:
            return
        LOGGER.log(level, "[GRAPH][run=%s] %s", self.run_id, message)

    def _duration_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def run_start(
        self,
        *,
        mode: str = "invoke",
        channel: Optional[str] = None,
        checkpointer: Optional[bool] = None,
        thread: Optional[str] = None,
    ) -> None:
        parts = ["START", f"mode={mode}"]
        if channel:
            parts.append(f"channel={channel}")
        if thread:
            parts.append(f"thread={sanitize(thread, 40)}")
        if self.session_id:
            parts.append(f"session={sanitize(self.session_id, 40)}")
        if self.turn_id:
            parts.append(f"turn={sanitize(str(self.turn_id), 40)}")
        if checkpointer is not None:
            parts.append(f"checkpointer={'on' if checkpointer else 'off'}")
        self._emit(" ".join(parts))

    def run_end(self, status: str = "success", extra: Optional[str] = None) -> None:
        for (name, _step), _started in list(self._open.items()):
            self._emit(f"[node={name}] END status=unreported duration_ms=-1", logging.WARNING)
        self._open.clear()
        message = f"END status={status} duration_ms={self._duration_ms()}"
        if extra:
            message += f" {sanitize(extra, 160)}"
        self._emit(
            message,
            logging.ERROR if status not in {"success", "finalized"} else logging.INFO,
        )

    def run_failed(self, error: BaseException) -> None:
        now = time.time()
        for (name, step), started in list(self._open.items()):
            duration = int(max(0.0, (now - started) * 1000))
            self._emit(
                f"[node={name}] END status=failed duration_ms={duration} step={step}",
                logging.WARNING,
            )
        self._open.clear()
        self._emit(
            f"END status=failed duration_ms={self._duration_ms()} "
            f"error={type(error).__name__}: {sanitize(str(error), 160)}",
            logging.ERROR,
        )

    # -- node events -------------------------------------------------------

    def debug_event(self, event: Any) -> None:
        """Consume one LangGraph ``stream_mode='debug'`` event."""
        if not isinstance(event, dict):
            return
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        etype = event.get("type")
        name = payload.get("name") or "?"
        step = event.get("step")
        if etype == "task":
            self.node_start(name, step, event.get("timestamp"), payload)
        elif etype == "task_result":
            self.node_end(name, step, event.get("timestamp"), payload)
        else:
            self._emit(f"event type={etype} ignored", logging.DEBUG)

    def node_start(self, name: str, step: Any, timestamp: Any, payload: Any = None) -> None:
        self._open[(name, step)] = _epoch(timestamp)
        message = f"[node={name}] START step={step}"
        if self._min <= 10 and isinstance(payload, dict) and payload.get("triggers"):
            message += f" triggers={sanitize(payload.get('triggers'), 80)}"
        self._emit(message)

    def node_end(self, name: str, step: Any, timestamp: Any, payload: Any = None) -> None:
        payload = payload if isinstance(payload, dict) else {}
        started = self._open.pop((name, step), None)
        ended = _epoch(timestamp)
        duration = int(max(0.0, (ended - started) * 1000)) if started is not None else -1
        error = payload.get("error")
        summary = self._summarize(name, payload.get("result"))
        message = (
            f"[node={name}] END "
            f"status={'error' if error else 'success'} duration_ms={duration}"
        )
        if summary:
            message += f" summary={sanitize(summary, 220)}"
        if error:
            message += f" error={sanitize(str(error), 140)}"
            self._emit(message, logging.WARNING)
        else:
            self._emit(message)

    # -- summaries (sanitized) --------------------------------------------

    def _summarize(self, name: str, result: Any) -> str:
        if not isinstance(result, dict):
            return ""
        if name == "tools":
            return self._summarize_tools(result)
        parts = []
        if name == "input_guardrail":
            if "input_valid" in result:
                parts.append(f"input_valid={result['input_valid']}")
        elif name == "output_guardrail":
            if "output_valid" in result:
                parts.append(f"valid={result['output_valid']}")
            if result.get("guardrail_feedback"):
                parts.append(f"feedback={sanitize(result['guardrail_feedback'], 110)}")
        elif name == "plan_step":
            messages = result.get("messages") or []
            if messages:
                last = messages[-1]
                tool_calls = getattr(last, "tool_calls", None)
                if tool_calls:
                    names = ",".join(
                        str(call.get("name")) for call in tool_calls if isinstance(call, dict)
                    )
                    parts.append(f"tool_calls={names}")
                else:
                    content = getattr(last, "content", "")
                    parts.append(
                        f"reply_chars={len(content) if isinstance(content, str) else 0}"
                    )
        elif name == "retry_node":
            parts.append(f"retry_count={result.get('retry_count')}")
        elif name == "handoff_to_human":
            parts.append(f"handoff={result.get('is_handoff')}")
            if result.get("handoff_reason"):
                parts.append(f"reason={result['handoff_reason']}")
        elif name == "persist_turn":
            # turn_number comes back from the real append_turn DB write.
            if result.get("turn_number") is not None:
                parts.append(f"event_written=yes turn_number={result['turn_number']}")
            if result.get("is_handoff"):
                parts.append("handoff=1")
        elif name == "persist_call":
            for key in ("finalized", "already_finalized", "empty_session", "working_events"):
                if result.get(key) is not None:
                    parts.append(f"{key}={result[key]}")
            if result.get("episode_outcome"):
                parts.append(f"episode_outcome={result['episode_outcome']}")
            if result.get("profile_facts_written") is not None:
                parts.append(f"profile_facts_written={len(result['profile_facts_written'])}")
            if result.get("persistence_warning"):
                parts.append(f"warning={sanitize(result['persistence_warning'], 80)}")
        elif name == "resolve_identity":
            parts.append(f"needs_identity={result.get('needs_identity')}")
        elif name == "build_call_brief":
            brief = result.get("call_brief") or {}
            if isinstance(brief, dict):
                parts.append(f"has_name={bool(brief.get('customer_name'))}")
                parts.append(f"has_phone={bool(brief.get('customer_phone'))}")
                parts.append(f"n_prev={brief.get('n_previous_sessions')}")
                parts.append(f"tools={len(brief.get('tool_summary') or [])}")
        if not parts:
            for key in ("input_valid", "output_valid", "status", "turn_number"):
                value = result.get(key)
                if isinstance(value, (bool, int, str)):
                    parts.append(f"{key}={value}")
        return sanitize(" ".join(str(part) for part in parts), 200)

    def _summarize_tools(self, result: Dict[str, Any]) -> str:
        messages = result.get("messages") or []
        lines = []
        for message in messages[:3]:
            tool_name = getattr(message, "name", None) or "tool"
            status = getattr(message, "status", None)
            content = getattr(message, "content", "")
            content_text = content if isinstance(content, str) else str(content)
            is_error = status == "error" or content_text.startswith("Error:")
            if is_error:
                code_match = _ERROR_CODE_RE.search(content_text)
                line = f"tool={tool_name} status=error"
                if code_match:
                    line += f" code={code_match.group(1)}"
                else:
                    line += f" detail={sanitize(content_text, 60)}"
                lines.append(line)
                continue
            extra = ""
            parsed: Any = None
            try:
                parsed = json.loads(content_text)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, dict) and "items" in parsed:
                items = parsed.get("items")
                count = len(items) if isinstance(items, list) else 0
                extra = f" results={count}"
            elif isinstance(parsed, dict):
                if parsed.get("status") == "error":
                    extra = " status=error"
                elif parsed.get("in_stock") is True:
                    extra = " in_stock=true"
                elif parsed.get("final_price_vnd") is not None:
                    extra = " quoted=yes"
            lines.append(f"tool={tool_name} status=success{extra}")
        hidden = len(messages) - 3
        if hidden > 0:
            lines.append(f"+{hidden} more")
        return sanitize("; ".join(lines), 200)

    # -- persistence -------------------------------------------------------

    def finalize(
        self,
        *,
        status: str,
        working_events: Optional[int] = None,
        episode: bool = False,
        already_finalized: bool = False,
        empty_session: bool = False,
        profile_facts_written: Any = None,
        warning: Optional[str] = None,
    ) -> None:
        parts = ["FINALIZE", f"status={status}"]
        if working_events is not None:
            parts.append(f"working_events={working_events}")
        parts.append(f"episode={'yes' if episode else 'no'}")
        if already_finalized:
            parts.append("already_finalized=yes")
        if empty_session:
            parts.append("empty_session=yes")
        if profile_facts_written is not None:
            parts.append(f"profile_facts_written={len(profile_facts_written)}")
        if warning:
            parts.append(f"warning={sanitize(warning, 80)}")
        self._emit(
            " ".join(parts),
            logging.WARNING if status == "failed" else logging.INFO,
        )



