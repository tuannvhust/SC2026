from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.api.routers.graph_runner import invoke_customer_turn, response_from_graph

router = APIRouter()

class CallTurnRequest(BaseModel):
    call_id: str
    speaker: str
    text: str
    turn_id: Optional[int] = None
    customer_id: Optional[str] = None
    session_id: Optional[str] = None
    channel: Optional[str] = "hotline"
    metadata: Optional[Dict[str, Any]] = None
    session_ended: bool = False

@router.post("/calls/turn")
def process_call_turn(request: CallTurnRequest):
    state = invoke_customer_turn(
        customer_id=request.customer_id,
        session_id=request.session_id or request.call_id,
        turn_id=str(request.turn_id) if request.turn_id is not None else None,
        message=request.text,
        channel=request.channel or "hotline",
        customer_info=request.metadata,
        session_ended=request.session_ended,
    )
    response = response_from_graph(state)
    return {
        "call_id": request.call_id,
        "processed": True,
        "status": "handed_off" if response["is_handoff"] else "in_progress",
        **response,
    }
