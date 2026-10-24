from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    # Conversation
    messages: Annotated[List[BaseMessage], add_messages]

    # Customer identity and CRM context
    customer_id: Optional[str]
    customer_info: Optional[Dict[str, Any]]
    # Ask-for-identity flow when CRM cannot resolve the caller.
    # needs_identity=True means the turn must pause to collect name+phone.
    needs_identity: bool
    identity_attempts: int
    # Which required identity slots are still missing (subset of phone/name).
    missing_identity_fields: Optional[List[str]]
    # Original Turn-1 request kept while asking for identity.
    pending_need: Optional[str]
    # Explicit identity resolution status: needs_input | invalid_input |
    # not_found | ambiguous | resolved | system_error
    identity_status: Optional[str]

    # Session continuity
    # Business date supplied by the caller/scenario (ISO YYYY-MM-DD).
    call_date: str
    call_brief: Optional[Dict[str, Any]]
    session_id: str
    session_started_at: str
    session_ended: bool
    session_outcome: Optional[str]
    turn_id: str
    turn_number: int
    # Safety
    input_valid: bool
    output_valid: bool
    guardrail_feedback: Optional[str]

    # Control flow
    is_handoff: bool
    handoff_reason: Optional[str]
    handoff_brief: Optional[Dict[str, Any]]
    # Tool invocation performed directly by the handoff node, outside ToolNode.
    trace_tool_calls: List[Dict[str, Any]]
    retry_count: int
