import json
import logging
import uuid
from datetime import date
from queue import Queue
from threading import Thread
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from src.api.routers.graph_runner import (
    _public_call_brief,
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
    call_date: Optional[date] = None


class ChatEndSessionRequest(BaseModel):
    session_id: str
    customer_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/chat/end-session")
def end_chat_session(request: ChatEndSessionRequest):
    logger.info(
        "[SESSION] END_SESSION_REQUESTED session_id=%s customer_id=%s",
        request.session_id,
        request.customer_id,
    )
    finalized = finalize_session(
        session_id=request.session_id,
        customer_id=request.customer_id,
        customer_info=request.metadata,
    )
    status = (
        "already_finalized"
        if finalized["already_finalized"]
        else ("empty_session" if finalized["empty_session"] else "finalized")
    )
    logger.info(
        "[SESSION] FINALIZE_CONFIRMED session_id=%s status=%s finalized=%s events=%s",
        request.session_id,
        status,
        finalized["finalized"],
        finalized.get("working_events", 0),
    )
    return {
        "finalized": finalized["finalized"],
        "already_finalized": finalized["already_finalized"],
        "empty_session": finalized["empty_session"],
        "status": status,
        **finalized,
    }


@router.post("/chat")
def handle_chat(request: ChatRequest):
    turn_id = request.turn_id or str(uuid.uuid4())

    def run_turn(on_call_brief=None):
        state = invoke_customer_turn(
            customer_id=request.customer_id,
            session_id=request.session_id,
            turn_id=turn_id,
            message=request.message,
            channel=request.channel or "web_chat",
            call_date=request.call_date,
            customer_info=request.metadata,
            session_ended=request.session_ended,
            on_call_brief=on_call_brief,
        )
        return response_from_graph(state)

    if request.stream:

        def stream_events():
            events = Queue()
            finished = object()

            def emit_call_brief(brief):
                events.put(
                    {
                        "type": "call_brief",
                        "call_brief": _public_call_brief(brief),
                    }
                )

            def run_streamed_turn():
                try:
                    response = run_turn(on_call_brief=emit_call_brief)
                    events.put(
                        {
                            "type": "response",
                            "text": response["reply"],
                            **response,
                        }
                    )
                except Exception as exc:
                    logger.exception("Chat streaming pipeline failed")
                    events.put(
                        {
                            "type": "error",
                            "error": (
                                "Phản hồi bị gián đoạn. Vui lòng thử lại. "
                                f"({type(exc).__name__})"
                            ),
                        }
                    )
                finally:
                    events.put(finished)

            Thread(target=run_streamed_turn, daemon=True).start()
            try:
                while True:
                    item = events.get()
                    if item is finished:
                        break
                    payload = json.dumps(item, ensure_ascii=False)
                    if item["type"] == "error":
                        yield f"event: error\ndata: {payload}\n\n"
                    else:
                        yield f"data: {payload}\n\n"
            except GeneratorExit:
                logger.debug("Chat stream closed by client before completion.")
            yield 'data: {"done": true}\n\n'

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return run_turn()
