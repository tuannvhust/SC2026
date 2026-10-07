"""Create and connect the application StateGraph."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.graph.nodes.input_nodes import (
    build_call_brief_node,
    input_guardrail_node,
    normalize_input_node,
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


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("input_guardrail", input_guardrail_node)
    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("resolve_identity", resolve_identity_node)
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
    workflow.add_edge("resolve_identity", "build_call_brief")
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
    return workflow.compile()


graph = build_graph()
