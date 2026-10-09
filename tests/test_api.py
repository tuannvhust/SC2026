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
    from src.api.routers import chat

    monkeypatch.setattr(
        chat,
        "process_raw_query_stream",
        lambda _message: iter(["Xin chào ", "anh/chị!"]),
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
    assert response.text == (
        'data: {"text": "Xin chào "}\n\n'
        'data: {"text": "anh/chị!"}\n\n'
        'data: {"done": true}\n\n'
    )


def test_chat_keeps_json_response_when_stream_is_not_requested(monkeypatch):
    from src.api.routers import chat

    monkeypatch.setattr(chat, "process_raw_query", lambda _message: "Câu trả lời.")

    response = TestClient(app).post(
        "/api/chat",
        json={"customer_id": "test", "message": "Samsung"},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Câu trả lời."
    assert response.json()["intent"] == "product"
