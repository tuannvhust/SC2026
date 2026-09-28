from .state import CallState


def route_after_plan(state: CallState) -> str:
    """Điều hướng sau bước lập kế hoạch: chuyển máy, gọi tool hoặc chuyển sang kiểm tra guardrail."""
    if state.get("plan_action") == "cannot_answer":
        return "handoff_to_human"
    if state.get("plan_action") == "call_tool":
        return "call_tool"
    return "guardrail_check"


def route_after_tool(state: CallState) -> str:
    """Điều hướng sau khi gọi tool: xử lý lỗi timeout, kiểm tra số lần gọi hoặc quay lại plan_step."""
    if state.get("needs_handoff"):
        return "handoff_to_human"
    if state.get("tool_call_count", 0) >= state.get("max_tool_calls", 3):
        return "guardrail_check"
    return "plan_step"


def route_after_guardrail(state: CallState) -> str:
    """Điều hướng sau guardrail: lưu dữ liệu nếu đạt, hoặc xử lý thất bại nếu vi phạm."""
    return "persist_turn" if state.get("guardrail_passed") else "handle_guardrail_failure"


def route_after_guardrail_failure(state: CallState) -> str:
    """Điều hướng khi guardrail vi phạm: chuyển máy nếu vượt ngưỡng retry, hoặc thử lập lại kế hoạch."""
    if state.get("retry_count", 0) >= state.get("max_retries", 2):
        return "handoff_to_human"
    return "plan_step"
