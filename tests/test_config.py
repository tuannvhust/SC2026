from src import config


def test_api_lifespan_initializes_and_closes_shared_connections(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import main

    lifecycle_calls = []
    monkeypatch.setattr(
        main,
        "get_shared_connections",
        lambda: lifecycle_calls.append("initialize"),
    )
    monkeypatch.setattr(
        main,
        "clear_components",
        lambda: lifecycle_calls.append("clear_components"),
    )
    monkeypatch.setattr(
        main,
        "warmup_reranker",
        lambda: lifecycle_calls.append("warmup_reranker"),
    )
    monkeypatch.setattr(
        main,
        "close_working_memory_store",
        lambda: lifecycle_calls.append("close_working_memory_store"),
    )
    monkeypatch.setattr(
        main,
        "close_shared_connections",
        lambda: lifecycle_calls.append("close"),
    )

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200

    assert lifecycle_calls == [
        "initialize",
        "warmup_reranker",
        "clear_components",
        "close_working_memory_store",
        "close",
    ]


def test_shared_connections_are_created_once_and_closed(monkeypatch):
    class FakeResource:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    class FakeEmbedder(FakeResource):
        def __init__(self):
            self.session = FakeResource()

    mongo_store = FakeResource()
    vector_store = FakeResource()
    dense_embedder = FakeEmbedder()
    monkeypatch.setattr(config, "MongoStore", lambda: mongo_store)
    monkeypatch.setattr(config, "QdrantVectorStore", lambda: vector_store)
    monkeypatch.setattr(config, "GeminiDenseEmbedder", lambda: dense_embedder)
    monkeypatch.setattr(config, "_connections", None)

    first = config.get_shared_connections()
    second = config.get_shared_connections()

    assert first is second
    assert first.mongo_store is mongo_store
    assert first.vector_store is vector_store
    assert first.dense_embedder is dense_embedder

    config.close_shared_connections()

    assert mongo_store.close_calls == 1
    assert vector_store.close_calls == 1
    assert dense_embedder.session.close_calls == 1
    assert config._connections is None


def test_fixed_sampling_gemini_model_does_not_receive_temperature(monkeypatch):
    captured = {}

    def create_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(config, "ChatGoogleGenerativeAI", create_model)

    config._build_chat_llm("gemini-3.6-flash", "test-key")

    assert captured == {
        "model": "gemini-3.6-flash",
        "google_api_key": "test-key",
        "max_retries": 1,
    }


def test_other_gemini_models_keep_configured_temperature(monkeypatch):
    captured = {}

    def create_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(config, "ChatGoogleGenerativeAI", create_model)

    config._build_chat_llm("gemini-2.5-flash", "test-key")

    assert captured["temperature"] == 0.3


def test_groq_model_uses_configured_model_and_key(monkeypatch):
    captured = {}

    def create_model(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(config, "ChatGroq", create_model)

    config._build_groq_llm("llama-test", "groq-test-key")

    assert captured == {
        "model": "llama-test",
        "groq_api_key": "groq-test-key",
        "temperature": 0.3,
        "max_retries": 2,
    }


def test_groq_fallback_runs_after_primary_failure():
    from langchain_core.runnables import RunnableLambda

    def fail(_value):
        raise RuntimeError("Gemini unavailable")

    chain = config.with_groq_fallback(
        RunnableLambda(fail),
        RunnableLambda(lambda _value: "Groq response"),
    )

    assert chain.invoke("prompt") == "Groq response"


def test_groq_fallback_is_optional():
    primary = object()

    assert config.with_groq_fallback(primary, None) is primary
