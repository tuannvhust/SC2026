from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.memory.semantic_rag.orchestrator import process_raw_query
from src.memory.semantic_rag.query_router import route

router = APIRouter()

class ChatRequest(BaseModel):
    customer_id: str
    message: str
    channel: Optional[str] = "chat"
    metadata: Optional[Dict[str, Any]] = None

@router.post("/chat")
def handle_chat(request: ChatRequest):
    route_result = route(request.message)
    return {
        "reply": process_raw_query(request.message),
        "sources": [],
        "intent": route_result["intent"]
    }
