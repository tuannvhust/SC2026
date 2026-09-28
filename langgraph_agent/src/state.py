import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class CallState(TypedDict, total=False):
    customer_phone: str
    channel: str
    call_id: str
    # operator.add => messages tự động tích lũy qua các node VÀ giữa các lượt thoại (nhờ checkpointer)
    messages: Annotated[List[Dict[str, str]], operator.add]

    customer_id: Optional[str]
    is_returning_customer: bool
    profile: Dict[str, Any]
    episodic_summaries: List[Dict[str, Any]]
    call_brief: Optional[str]
    retrieved_kb: List[Dict[str, Any]]

    plan_action: str
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    draft_response: Optional[str]
    tool_call_count: int
    max_tool_calls: int

    guardrail_passed: bool
    guardrail_violation_reason: Optional[str]
    retry_count: int
    max_retries: int
    needs_handoff: bool
    handoff_reason: Optional[str]
    handoff_brief: Optional[str]

    final_response: Optional[str]
    call_outcome: Optional[str]
    facts_to_persist: Dict[str, Any]
