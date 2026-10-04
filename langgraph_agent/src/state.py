import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class CallState(TypedDict, total=False):
    scenario_id: str
    run_id: str
    config: str
    call: str
    turn: int
    call_date: str
    input_mode: str
    channel_identity: str
    raw_customer_text: str
    normalized_customer_text: str
    orders: List[Dict[str, Any]]
    customer_phone: str
    channel: str
    call_id: str
    # operator.add => messages tự động tích lũy qua các node VÀ giữa các lượt thoại (nhờ checkpointer)
    messages: Annotated[List[Dict[str, str]], operator.add]

    customer_id: Optional[str]
    customer_name: Optional[str]
    honorific: Optional[str]
    crm_result: Dict[str, Any]
    needs_identity_confirm: bool
    candidates: List[Dict[str, Any]]
    is_returning_customer: bool
    profile: Dict[str, Any]
    episodic_summaries: List[Dict[str, Any]]
    call_brief: Optional[Dict[str, Any]]
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
    working_memory: Dict[str, Any]
    long_term_facts: Dict[str, Any]
    facts_used: List[str]
    questions: List[Dict[str, Any]]
    claims: List[Dict[str, Any]]
    memory_writes: List[Dict[str, Any]]
    trace_path: Optional[str]
    latency: Dict[str, Any]
    call_brief_latency_ms: Optional[int]
    confirmed_slots: List[str]
    pending_trace: Dict[str, Any]
