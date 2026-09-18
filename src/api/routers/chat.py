from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any

router = APIRouter()

class ChatRequest(BaseModel):
    customer_id: str
    message: str
    channel: Optional[str] = "chat"
    metadata: Optional[Dict[str, Any]] = None

@router.post("/chat")
def handle_chat(request: ChatRequest):
    return {
        "reply": "Dạ em chào anh/chị, em có thể hỗ trợ gì cho anh/chị ạ?",
        "sources": [],
        "intent": "chitchat"
    }

