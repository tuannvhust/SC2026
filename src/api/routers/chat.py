import json
import logging
import uuid
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.api.routers.graph_runner import (
    finalize_session,
    invoke_customer_turn,
    response_from_graph,
)

router = APIRouter()
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    customer_id: str
    message: str
    channel: Optional[str] = "chat"
    metadata: Optional[Dict[str, Any]] = None
    stream: bool = False
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    session_ended: bool = False

class ChatEndSessionRequest(BaseModel):
    session_id: str
    customer_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/chat/end-session")
def end_chat_session(request: ChatEndSessionRequest):
    finalized = finalize_session(
        session_id=request.session_id,
        customer_id=request.customer_id,
        customer_info=request.metadata,
    )
    return {
        "finalized": finalized["finalized"],
        "already_finalized": finalized["already_finalized"],
        "empty_session": finalized["empty_session"],
        "status": "already_finalized"
        if finalized["already_finalized"]
        else ("empty_session" if finalized["empty_session"] else "finalized"),
        **finalized,
    }


@router.post("/chat")
def handle_chat(request: ChatRequest):
    turn_id = request.turn_id or str(uuid.uuid4())

    def run_turn():
        state = invoke_customer_turn(
            customer_id=request.customer_id,
            session_id=request.session_id,
            turn_id=turn_id,
            message=request.message,
            channel=request.channel or "web_chat",
            customer_info=request.metadata,
            session_ended=request.session_ended,
        )
        return response_from_graph(state)

    if request.stream:
        def stream_events():
            try:
                response = run_turn()
                payload = json.dumps(
                    {"text": response["reply"], **response},
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
            except Exception as exc:
                logger.exception("Chat streaming pipeline failed")
                payload = json.dumps(
                    {
                        "error": (
                            "Phản hồi bị gián đoạn. Vui lòng thử lại. "
                            f"({type(exc).__name__})"
                        )
                    },
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

    return run_turn()
