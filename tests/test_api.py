import codecs
import json

from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from src.api.main import app


def test_health_endpoint():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_validates_required_fields():
    response = TestClient(app).post("/api/chat", json={"message": "Samsung"})

    assert response.status_code == 422


def test_chat_stream_returns_server_sent_events(monkeypatch):
    from langchain_core.messages import AIMessage
    from src.api.routers import chat

    monkeypatch.setattr(
        chat,
        "invoke_customer_turn",
        lambda **kwargs: {
            "messages": [AIMessage(content="Xin chào anh/chị!")],
            "session_id": kwargs["session_id"],
            "turn_id": kwargs["turn_id"],
        },
    )

    response = TestClient(app).post(
        "/api/chat",
        json={
            "customer_id": "test",
            "message": "Samsung",
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"reply": "Xin chào anh/chị!"' in response.text
    assert 'data: {"done": true}\n\n' in response.text


def test_identity_prompt_round_trips_as_utf8_in_json_and_split_sse(monkeypatch):
    from src.api.routers import chat
    from src.graph.nodes.input_nodes import request_identity_node

    expected = (
        "Dạ em chưa nhận diện được thông tin của mình ạ. "
        "Mình cho em xin tên và số điện thoại để em hỗ trợ chính xác hơn nhé ạ?"
    )
    identity_result = request_identity_node(
        {
            "messages": [HumanMessage(content="Xin tư vấn")],
            "missing_identity_fields": ["phone", "name"],
            "customer_info": {},
        }
    )
    assert identity_result["messages"][0].content == expected

    def invoke(**kwargs):
        return {
            **identity_result,
            "session_id": kwargs["session_id"],
            "turn_id": kwargs["turn_id"],
        }

    monkeypatch.setattr(chat, "invoke_customer_turn", invoke)
    client = TestClient(app)
    request_data = {
        "customer_id": "",
        "session_id": "SESSION-VIETNAMESE",
        "message": "Xin tư vấn",
    }

    json_response = client.post("/api/chat", json=request_data)
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    assert json_response.content.decode("utf-8")
    assert json_response.json()["reply"] == expected

    sse_response = client.post(
        "/api/chat", json={**request_data, "stream": True}
    )
    assert sse_response.status_code == 200
    assert sse_response.headers["content-type"] == (
        "text/event-stream; charset=utf-8"
    )

    decoder = codecs.getincrementaldecoder("utf-8")()
    decoded_chunks = []
    for chunk in sse_response.iter_bytes(chunk_size=1):
        decoded_chunks.append(decoder.decode(chunk, final=False))
    decoded_chunks.append(decoder.decode(b"", final=True))
    sse_text = "".join(decoded_chunks)

    assert "Dạ" in sse_text
    assert "chưa nhận diện" in sse_text
    assert "điện thoại" in sse_text
    assert "hỗ trợ chính xác" in sse_text
    response_event = next(
        line.removeprefix("data: ")
        for line in sse_text.splitlines()
        if line.startswith('data: {"type": "response"')
    )
    assert json.loads(response_event)["reply"] == expected


def test_chat_keeps_json_response_when_stream_is_not_requested(monkeypatch):
    from src.api.routers import chat

    from langchain_core.messages import AIMessage

    captured = {}

    def invoke(**kwargs):
        captured.update(kwargs)
        return {
            "messages": [AIMessage(content="Câu trả lời.")],
            "session_id": kwargs["session_id"],
            "turn_id": kwargs["turn_id"],
            "turn_number": 1,
        }

    monkeypatch.setattr(chat, "invoke_customer_turn", invoke)

    response = TestClient(app).post(
        "/api/chat",
        json={
            "customer_id": "test",
            "session_id": "session-1",
            "message": "Samsung",
            "channel": "chat",
            "metadata": {"phone": "0901234567"},
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Câu trả lời."
    assert response.json()["session_id"] == "session-1"
    assert captured["customer_id"] == "test"
    assert captured["channel"] == "chat"
    assert captured["customer_info"] == {"phone": "0901234567"}


def test_calls_turn_invokes_graph_with_call_context(monkeypatch):
    from langchain_core.messages import AIMessage
    from src.api.routers import calls

    captured = {}

    def invoke(**kwargs):
        captured.update(kwargs)
        return {
            "messages": [AIMessage(content="Em đang hỗ trợ mình ạ.")],
            "session_id": kwargs["session_id"],
            "turn_id": kwargs["turn_id"],
            "is_handoff": False,
        }

    monkeypatch.setattr(calls, "invoke_customer_turn", invoke)
    response = TestClient(app).post(
        "/api/calls/turn",
        json={
            "call_id": "call-1",
            "customer_id": "customer-1",
            "speaker": "customer",
            "text": "Tôi cần hỗ trợ",
            "turn_id": 2,
            "channel": "hotline",
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Em đang hỗ trợ mình ạ."
    assert captured["customer_id"] == "customer-1"
    assert captured["session_id"] == "call-1"
    assert captured["turn_id"] == "2"
    assert captured["channel"] == "hotline"


def test_chat_end_session_success(monkeypatch):
    from src.api.routers import chat

    captured = {}

    def mock_finalize(session_id, customer_id=None, customer_info=None):
        captured["session_id"] = session_id
        captured["customer_id"] = customer_id
        return {
            "session_id": session_id,
            "customer_id": customer_id,
            "finalized": True,
            "already_finalized": False,
            "empty_session": False,
            "working_events": 3,
            "episode": {"outcome": "completed"},
            "episode_outcome": "completed",
            "profile_facts_written": ["interest"],
            "profile_facts": {},
            "persistence_warning": None,
        }

    monkeypatch.setattr(chat, "finalize_session", mock_finalize)

    response = TestClient(app).post(
        "/api/chat/end-session",
        json={"session_id": "sess-123", "customer_id": "cust-abc"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["finalized"] is True
    assert data["status"] == "finalized"
    assert data["working_events"] == 3
    assert captured["session_id"] == "sess-123"
    assert captured["customer_id"] == "cust-abc"


def test_chat_end_session_idempotent_duplicate(monkeypatch):
    from src.api.routers import chat

    def mock_finalize(session_id, customer_id=None, customer_info=None):
        return {
            "session_id": session_id,
            "customer_id": customer_id,
            "finalized": True,
            "already_finalized": True,
            "empty_session": False,
            "working_events": 3,
            "episode": {"outcome": "completed"},
            "episode_outcome": "completed",
            "profile_facts_written": [],
            "profile_facts": {},
            "persistence_warning": None,
        }

    monkeypatch.setattr(chat, "finalize_session", mock_finalize)

    response = TestClient(app).post(
        "/api/chat/end-session",
        json={"session_id": "sess-123", "customer_id": "cust-abc"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["finalized"] is True
    assert data["already_finalized"] is True
    assert data["status"] == "already_finalized"


def test_chat_end_session_missing_required_session_id():
    response = TestClient(app).post(
        "/api/chat/end-session",
        json={"customer_id": "cust-abc"},
    )
    assert response.status_code == 422
