from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter()

class CallTurnRequest(BaseModel):
    call_id: str
    speaker: str
    text: str
    turn_id: Optional[int] = 1

@router.post("/calls/turn")
def process_call_turn(request: CallTurnRequest):
    return {
        "call_id": request.call_id,
        "processed": True,
        "status": "in_progress"
    }

