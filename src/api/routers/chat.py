import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.memory.semantic_rag.orchestrator import (
    process_raw_query,
    process_raw_query_stream,
)
from src.memory.semantic_rag.query_router import route

router = APIRouter()
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    customer_id: str
    message: str
    channel: Optional[str] = "chat"
    metadata: Optional[Dict[str, Any]] = None
    stream: bool = False

@router.post("/chat")
def handle_chat(request: ChatRequest):
    if request.stream:
        def stream_events():
            try:
                for text in process_raw_query_stream(request.message):
                    payload = json.dumps({"text": text}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
            except Exception:
                logger.exception("Chat streaming pipeline failed")
                payload = json.dumps(
                    {"error": "Phản hồi bị gián đoạn. Vui lòng thử lại."},
                    ensure_ascii=False,
                )
                yield f"event: error\ndata: {payload}\n\n"
            yield 'data: {"done": true}\n\n'

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    route_result = route(request.message)
    return {
        "reply": process_raw_query(request.message),
        "sources": [],
        "intent": route_result["intent"]
    }
