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
