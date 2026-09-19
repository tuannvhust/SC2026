from fastapi.testclient import TestClient

from src.api.main import app


def test_health_endpoint():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_validates_required_fields():
    response = TestClient(app).post("/api/chat", json={"message": "Samsung"})

    assert response.status_code == 422
