from fastapi.testclient import TestClient

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
