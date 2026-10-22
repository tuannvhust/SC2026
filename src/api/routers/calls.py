from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.api.routers.graph_runner import (
    finalize_session,
    invoke_customer_turn,
    response_from_graph,
)

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

class CallEndSessionRequest(BaseModel):
    call_id: str
    session_id: Optional[str] = None
    customer_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@router.post("/calls/end-session")
def end_call_session(request: CallEndSessionRequest):
    session_id = request.session_id or request.call_id
    finalized = finalize_session(
        session_id=session_id,
        customer_id=request.customer_id,
        customer_info=request.metadata,
    )
    return {
        "call_id": request.call_id,
        "finalized": finalized["finalized"],
        "already_finalized": finalized["already_finalized"],
        "empty_session": finalized["empty_session"],
        "status": "already_finalized"
        if finalized["already_finalized"]
        else ("empty_session" if finalized["empty_session"] else "finalized"),
        **finalized,
    }

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
