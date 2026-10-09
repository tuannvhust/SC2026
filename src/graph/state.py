from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    # Conversation
    messages: Annotated[List[BaseMessage], add_messages]

    # Customer identity and CRM context
    customer_id: Optional[str]
    customer_info: Optional[Dict[str, Any]]

    # Session continuity
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
    retry_count: int
