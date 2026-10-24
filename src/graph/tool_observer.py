"""Structured tool execution observer for all M1/M2 tools.

Emits consistent log lines at tool call boundaries:

    [TOOL][run=abc][tool=catalog.search] START call_id=xyz query="máy lọc" ...
    [TOOL][run=abc][tool=catalog.search] END status=success results=3 duration_ms=420
    [TOOL][run=abc][tool=catalog.search] END status=error error=APIError duration_ms=38

Verbosity is controlled with ``TOOL_LOG_LEVEL``:
  ``silent`` / ``off`` — no tool logs
  ``warn``             — only failures and empty results
  ``info`` (default)   — start + end summary
  ``debug``            — include sanitized input args and top-N result details

Output is via the ``src.graph.tool_observer`` logger so it inherits the
application log handler without creating duplicate handlers.

Privacy rules:
- Phone numbers (0xxxxxxxxx) masked to ``0***``.
- API keys / tokens / secrets masked.
- Customer name, customer_id, session_id logged only as length or presence flag.
- Result payloads truncated to RESULT_PREVIEW_CHARS.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("src.graph.tool_observer")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_LEVEL_MAP = {"silent": 99, "off": 99, "warn": 30, "warning": 30, "info": 20, "debug": 10}
_QUERY_MAX_CHARS = int(os.getenv("TOOL_LOG_QUERY_MAX", "200"))
_RESULT_PREVIEW_CHARS = int(os.getenv("TOOL_LOG_RESULT_MAX", "400"))
_TOP_N_RESULTS = int(os.getenv("TOOL_LOG_TOP_N", "5"))


def _min_level() -> int:
    raw = os.getenv("TOOL_LOG_LEVEL", "info").strip().lower()
    return _LEVEL_MAP.get(raw, 20)


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

_PHONE_RE = re.compile(r"(?<!\d)(0\d{9})(?!\d)")
_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|token|secret|password|authorization)\b\s*[:=]\s*\S+"
)
_PII_KEYS = frozenset(
    {"name", "customer_name", "full_name", "preferred_name", "customer_id", "session_id"}
)


def _sanitize(text: Any, limit: int = _QUERY_MAX_CHARS) -> str:
    """Collapse, mask phones/secrets, and cap length."""
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


def _sanitize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of args with PII keys replaced by presence flags."""
    out: Dict[str, Any] = {}
    for key, value in args.items():
        if key in _PII_KEYS:
            if isinstance(value, str):
                out[key] = f"<{len(value)}chars>"
            elif value is None:
                out[key] = None
            else:
                out[key] = "<present>"
        elif isinstance(value, str):
            out[key] = _sanitize(value, _QUERY_MAX_CHARS)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Result summarization
# ---------------------------------------------------------------------------

_STATUS_SUCCESS = "success"
_STATUS_EMPTY = "success_empty"
_STATUS_ERROR = "error"
_STATUS_PARTIAL = "partial"


def _classify_result(tool_name: str, result: Any) -> tuple[str, str, int]:
    """Return (status, summary_line, result_count).

    Distinguishes success / success_empty / error / partial strictly:
    - error: result contains 'error' key with a non-None value.
    - success_empty: query succeeded but returned 0 items.
    - success: query succeeded and returned >= 1 item.
    """
    if not isinstance(result, dict):
        text = _sanitize(str(result), _RESULT_PREVIEW_CHARS)
        return _STATUS_SUCCESS, text, 0

    # Error field present and non-null.
    error_val = result.get("error")
    if error_val:
        return _STATUS_ERROR, _sanitize(str(error_val), 200), 0

    # catalog.search / list-returning tools.
    for list_key in ("items", "products", "results"):
        if list_key in result and isinstance(result[list_key], list):
            items = result[list_key]
            count = len(items)
            status = _STATUS_EMPTY if count == 0 else _STATUS_SUCCESS
            top = []
            for item in items[:_TOP_N_RESULTS]:
                if isinstance(item, dict):
                    sku = item.get("sku") or item.get("product_id") or "?"
                    name = item.get("name") or ""
                    score = item.get("score") or item.get("relevance_score")
                    cat = item.get("category") or ""
                    parts = [f"sku={sku}"]
                    if name:
                        parts.append(f"name={_sanitize(name, 40)}")
                    if cat:
                        parts.append(f"cat={cat}")
                    if score is not None:
                        parts.append(f"score={score:.3f}" if isinstance(score, float) else f"score={score}")
                    top.append("[" + " ".join(parts) + "]")
            summary = f"count={count}"
            if top:
                summary += " top=" + ",".join(top)
            return status, _sanitize(summary, _RESULT_PREVIEW_CHARS), count


    # Single-item tools (pricing.get_quote, inventory.check, etc.)
    if "final_price_vnd" in result:
        sku = result.get("sku") or "?"
        price = result.get("final_price_vnd")
        gifts = len(result.get("gifts") or [])
        return _STATUS_SUCCESS, f"sku={sku} price={price} gifts={gifts}", 1

    if "in_stock" in result:
        sku = result.get("sku") or "?"
        stock = result.get("in_stock")
        qty = result.get("qty") or result.get("stock")
        return _STATUS_SUCCESS, f"sku={sku} in_stock={stock} qty={qty}", 1

    if result.get("status") == "error":
        return _STATUS_ERROR, _sanitize(str(result), 200), 0

    # Generic dict — cap and return.
    return _STATUS_SUCCESS, _sanitize(str(result), _RESULT_PREVIEW_CHARS), 1


# ---------------------------------------------------------------------------
# Observer context (injected per graph run)
# ---------------------------------------------------------------------------

class _ToolContext:
    """Lightweight per-run context passed to wrapped tools."""

    __slots__ = ("run_id", "session_id", "turn_id")

    def __init__(
        self,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
    ) -> None:
        self.run_id = run_id or "?"
        self.session_id = session_id
        self.turn_id = turn_id


# Module-level active context (set by graph runner before each invocation).
_active_ctx: _ToolContext = _ToolContext()


def set_run_context(
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> None:
    """Register the current graph run context for tool log correlation.

    Call this before each graph invocation so tool logs carry the same
    run_id/session_id/turn_id as the node-level trace.
    """
    global _active_ctx
    _active_ctx = _ToolContext(run_id=run_id, session_id=session_id, turn_id=turn_id)


# ---------------------------------------------------------------------------
# Core logging functions
# ---------------------------------------------------------------------------

def _log_tool_start(
    tool_name: str,
    call_id: Optional[str],
    args: Dict[str, Any],
    level: int,
) -> None:
    if level >= 99 or logger.level > logging.DEBUG:
        return
    if _min_level() > logging.DEBUG:
        return
    ctx = _active_ctx
    sanitized = _sanitize_args(args)
    logger.debug(
        "[TOOL][run=%s][tool=%s] START call_id=%s args=%s",
        ctx.run_id,
        tool_name,
        call_id or "?",
        _sanitize(str(sanitized), _QUERY_MAX_CHARS),
    )


def _log_tool_end(
    tool_name: str,
    call_id: Optional[str],
    status: str,
    summary: str,
    result_count: int,
    duration_ms: int,
    error: Optional[Exception] = None,
) -> None:
    min_level = _min_level()
    if min_level >= 99:
        return

    ctx = _active_ctx
    prefix = f"[TOOL][run={ctx.run_id}][tool={tool_name}]"

    if error is not None or status == _STATUS_ERROR:
        msg = (
            f"{prefix} END status={status} duration_ms={duration_ms} "
            f"error={type(error).__name__ if error else 'tool_error'} "
            f"detail={_sanitize(str(error or summary), 200)}"
        )
        logger.warning(msg)
        return

    if status == _STATUS_EMPTY:
        logger.info(
            "%s END status=success_empty duration_ms=%s results=0",
            prefix,
            duration_ms,
        )
        return


    if min_level <= logging.INFO:
        logger.info(
            "%s END status=%s results=%s duration_ms=%s %s",
            prefix,
            status,
            result_count,
            duration_ms,
            _sanitize(summary, _RESULT_PREVIEW_CHARS),
        )


# ---------------------------------------------------------------------------
# Decorator / wrapper
# ---------------------------------------------------------------------------

def observe_tool(tool_fn: Any) -> Any:
    """Wrap a LangChain @tool so every invocation emits structured logs.

    Works with both direct ``.invoke(args)`` calls (used by ToolNode) and
    plain function calls.  The wrapped function returns the original result
    unchanged so graph behavior is not affected.
    """
    original_invoke = getattr(tool_fn, "invoke", None)
    tool_name: str = getattr(tool_fn, "name", None) or getattr(tool_fn, "__name__", "unknown")

    if original_invoke is not None:
        # LangChain StructuredTool: patch the invoke method.
        @wraps(original_invoke)
        def _patched_invoke(input_args: Any, *args_rest: Any, **kwargs: Any) -> Any:
            call_id: Optional[str] = None
            if isinstance(input_args, dict):
                call_id = input_args.get("tool_call_id")
                log_args = _sanitize_args(input_args)
            else:
                log_args = {"_input": _sanitize(str(input_args), _QUERY_MAX_CHARS)}

            min_level = _min_level()
            if min_level < 99:
                _log_tool_start(tool_name, call_id, log_args if isinstance(input_args, dict) else {}, min_level)

            t0 = time.perf_counter()
            exc: Optional[Exception] = None
            result: Any = None
            try:
                result = original_invoke(input_args, *args_rest, **kwargs)
                return result
            except Exception as error:
                exc = error
                raise
            finally:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                if exc is not None:
                    _log_tool_end(tool_name, call_id, _STATUS_ERROR, "", 0, duration_ms, exc)
                else:
                    status, summary, count = _classify_result(tool_name, result)
                    _log_tool_end(tool_name, call_id, status, summary, count, duration_ms)

        try:
            tool_fn.invoke = _patched_invoke  # type: ignore[attr-defined]
        except (ValueError, TypeError):
            object.__setattr__(tool_fn, "invoke", _patched_invoke)

    return tool_fn



def observe_tools(tools: Sequence[Any]) -> List[Any]:
    """Apply ``observe_tool`` to a list of tools and return the same list."""
    for tool in tools:
        observe_tool(tool)
    return list(tools)


# ---------------------------------------------------------------------------
# Catalog.search specific detail logger (called from tool_repository)
# ---------------------------------------------------------------------------

def log_catalog_search_detail(
    *,
    run_id: Optional[str] = None,
    query: str,
    sku: Optional[str],
    category: Optional[str],
    top_k: int,
    backend: str,
    candidates_before_rerank: int,
    candidates_after_rerank: int,
    supabase_products: int,
    supabase_variants: int,
    final_items: int,
    duration_ms: int,
    status: str,
    top_results: Optional[List[Dict[str, Any]]] = None,
    error: Optional[str] = None,
) -> None:
    """Emit a single DEBUG line with full catalog.search execution details.

    Called from within ``catalog_search`` implementation to give visibility
    into query routing, vector search results, Supabase hydration, and
    reranking outcome — without polluting INFO logs.
    """
    if _min_level() > logging.DEBUG:
        return
    ctx = _active_ctx
    run = run_id or ctx.run_id
    top_skus: List[str] = []
    if top_results:
        for item in top_results[:_TOP_N_RESULTS]:
            if isinstance(item, dict):
                sku_val = item.get("sku") or item.get("product_id") or "?"
                score = item.get("score") or item.get("relevance_score")
                entry = f"{sku_val}"
                if score is not None:
                    entry += f"({score:.3f})" if isinstance(score, float) else f"({score})"
                top_skus.append(entry)
    logger.debug(
        "[TOOL][run=%s][tool=catalog.search] DETAIL "
        "query=%s sku=%s cat=%s top_k=%s backend=%s "
        "candidates_before=%s candidates_after=%s "
        "supabase_products=%s supabase_variants=%s "
        "final_items=%s duration_ms=%s status=%s "
        "top=[%s]%s",
        run,
        _sanitize(query, _QUERY_MAX_CHARS),
        sku or "none",
        category or "none",
        top_k,
        backend,
        candidates_before_rerank,
        candidates_after_rerank,
        supabase_products,
        supabase_variants,
        final_items,
        duration_ms,
        status,
        ", ".join(top_skus),
        f" error={_sanitize(error, 120)}" if error else "",
    )

