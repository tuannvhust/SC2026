"""Create and connect the application StateGraph."""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

logger = logging.getLogger(__name__)

from src.graph.nodes.input_nodes import (
    MAX_IDENTITY_ATTEMPTS,
    build_call_brief_node,
    input_guardrail_node,
    normalize_input_node,
    request_identity_node,
    resolve_identity_node,
)
from src.graph.nodes.persistence_nodes import persist_call_node, persist_turn_node
from src.graph.nodes.planner import plan_step_node
from src.graph.nodes.safety_nodes import (
    handoff_to_human_node,
    output_guardrail_node,
    retry_node,
    route_after_retry,
)
from src.graph.state import AgentState
from src.tools.tool_repository import M1_TOOLS

tool_node = ToolNode(M1_TOOLS, handle_tool_errors=True)


def route_after_guardrail(
    state: AgentState,
) -> Literal["normalize_input", "persist_turn"]:
    """Skip planning for invalid customer input."""
    return "normalize_input" if state.get("input_valid", False) else "persist_turn"


def route_after_identity(
    state: AgentState,
) -> Literal["request_identity", "build_call_brief"]:
    """Pause to collect name+phone when CRM cannot resolve the caller.

    Falls back to guest mode after MAX_IDENTITY_ATTEMPTS so the session can
    still continue to build_call_brief without a resolved customer_id.
    """
    if not state.get("needs_identity", False):
        return "build_call_brief"
    if int(state.get("identity_attempts") or 0) >= MAX_IDENTITY_ATTEMPTS:
        return "build_call_brief"
    return "request_identity"


def route_after_plan(state: AgentState) -> Literal["tools", "output_guardrail"]:
    """Send requested tools to ToolNode and final responses to safety checks."""
    messages = state.get("messages", [])
    if messages and getattr(messages[-1], "tool_calls", None):
        return "tools"
    return "output_guardrail"


def route_after_output_guardrail(
    state: AgentState,
) -> Literal["persist_turn", "retry_node"]:
    return "persist_turn" if state.get("output_valid", False) else "retry_node"


def route_after_persist_turn(
    state: AgentState,
) -> Literal["persist_call", "__end__"]:
    """Commit episodic/profile memory only after the caller ends the session."""
    return "persist_call" if state.get("session_ended", False) else END


def build_graph(checkpointer=None):
    workflow = StateGraph(AgentState)

    workflow.add_node("input_guardrail", input_guardrail_node)
    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("resolve_identity", resolve_identity_node)
    workflow.add_node("request_identity", request_identity_node)
    workflow.add_node("build_call_brief", build_call_brief_node)
    workflow.add_node("plan_step", plan_step_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("output_guardrail", output_guardrail_node)
    workflow.add_node("retry_node", retry_node)
    workflow.add_node("handoff_to_human", handoff_to_human_node)
    workflow.add_node("persist_turn", persist_turn_node)
    workflow.add_node("persist_call", persist_call_node)

    workflow.add_edge(START, "input_guardrail")
    workflow.add_conditional_edges("input_guardrail", route_after_guardrail)
    workflow.add_edge("normalize_input", "resolve_identity")
    workflow.add_conditional_edges("resolve_identity", route_after_identity)
    workflow.add_edge("request_identity", "persist_turn")
    workflow.add_edge("build_call_brief", "plan_step")

    workflow.add_conditional_edges("plan_step", route_after_plan)
    workflow.add_edge("tools", "plan_step")

    workflow.add_conditional_edges(
        "output_guardrail",
        route_after_output_guardrail,
    )
    workflow.add_conditional_edges(
        "retry_node",
        route_after_retry,
        {"plan_step": "plan_step", "handoff_to_human": "handoff_to_human"},
    )
    workflow.add_edge("handoff_to_human", "persist_turn")

    workflow.add_conditional_edges(
        "persist_turn",
        route_after_persist_turn,
        {"persist_call": "persist_call", END: END},
    )
    workflow.add_edge("persist_call", END)
    return workflow.compile(checkpointer=checkpointer)


class GraphRuntime:
    """Stable graph handle that can receive its persistent checkpointer at startup."""

    def __init__(self):
        self._graph = build_graph()
        self.checkpointer_enabled = False

    def invoke(self, *args, **kwargs):
        return self._graph.invoke(*args, **kwargs)

    def astream(self, *args, **kwargs):
        return self._graph.astream(*args, **kwargs)

    def install_checkpointer(self, checkpointer):
        self._graph = build_graph(checkpointer=checkpointer)
        self.checkpointer_enabled = True


graph = GraphRuntime()

_checkpointer_pool = None
_async_checkpointer_pool = None


_CHECKPOINTER_POOL_KWARGS = {
    "autocommit": True,
    "prepare_threshold": 0,
    # Keep idle Supabase connections alive; direct :5432 often drops them.
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
}


def _is_pool_connection_error(error: Exception) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    return any(
        marker in text
        for marker in (
            "pool-1",
            "connection failed",
            "server closed the connection",
            "connection to server",
            "operationalerror",
            "ssl",
            "timeout",
        )
    )


def initialize_graph_checkpointer() -> None:
    """Connect LangGraph checkpoints to the configured PostgreSQL database."""
    global _checkpointer_pool
    if graph.checkpointer_enabled:
        return

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    from src.memory.working.postgres_store import (
        checkpointer_database_url,
        describe_database_url,
    )

    conninfo = checkpointer_database_url()
    logger.info("checkpointer database: %s", describe_database_url(conninfo))
    _checkpointer_pool = ConnectionPool(
        conninfo=conninfo,
        min_size=1,
        max_size=5,
        timeout=10,
        kwargs=_CHECKPOINTER_POOL_KWARGS,
        open=True,
    )
    checkpointer = PostgresSaver(_checkpointer_pool)
    checkpointer.setup()
    graph.install_checkpointer(checkpointer)


def close_graph_checkpointer() -> None:
    global _checkpointer_pool
    if _checkpointer_pool is not None:
        _checkpointer_pool.close()
        _checkpointer_pool = None
    graph.checkpointer_enabled = False


async def initialize_graph_async_checkpointer() -> None:
    """Install an async PostgreSQL checkpointer for graph.astream()."""
    global _async_checkpointer_pool
    if graph.checkpointer_enabled:
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

    from src.memory.working.postgres_store import (
        checkpointer_database_url,
        describe_database_url,
    )

    conninfo = checkpointer_database_url()
    logger.info("async checkpointer database: %s", describe_database_url(conninfo))
    _async_checkpointer_pool = AsyncConnectionPool(
        conninfo=conninfo,
        min_size=1,
        max_size=5,
        timeout=10,
        kwargs=_CHECKPOINTER_POOL_KWARGS,
        open=False,
    )
    await _async_checkpointer_pool.open()
    checkpointer = AsyncPostgresSaver(_async_checkpointer_pool)
    await checkpointer.setup()
    graph.install_checkpointer(checkpointer)


async def reopen_graph_async_checkpointer() -> None:
    """Close a stale pool and reconnect once (Turn 2+ pool-1 recovery)."""
    await close_graph_async_checkpointer()
    await initialize_graph_async_checkpointer()


async def close_graph_async_checkpointer() -> None:
    global _async_checkpointer_pool
    if _async_checkpointer_pool is not None:
        await _async_checkpointer_pool.close()
        _async_checkpointer_pool = None
    graph.checkpointer_enabled = False
