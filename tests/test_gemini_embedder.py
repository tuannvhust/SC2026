from unittest.mock import Mock, patch

from src.services.gemini_embedder import GeminiDenseEmbedder


def test_gemini_embedder_uses_configured_model_and_normalizes_dimension():
    response = Mock(status_code=200)
    response.json.return_value = {"embedding": {"values": [0.5] * 768}}

    with patch("src.services.gemini_embedder.requests.post", return_value=response) as post:
        values = GeminiDenseEmbedder(
            model_name="models/test-embedding",
            api_key="test-key",
        ).embed_text("Samsung")

    assert len(values) == 768
    assert values[:2] == [0.5, 0.5]
    assert "models/test-embedding:embedContent" in post.call_args.args[0]
    assert post.call_args.kwargs["params"] == {"key": "test-key"}
    assert "key=" not in post.call_args.args[0]
    assert post.call_args.kwargs["timeout"] == 60


def test_gemini_embedder_uses_configured_timeout(monkeypatch):
    monkeypatch.setenv("GEMINI_EMBEDDING_TIMEOUT", "90")
    response = Mock(status_code=200)
    response.json.return_value = {"embedding": {"values": [0.5] * 768}}

    with patch(
        "src.services.gemini_embedder.requests.post",
        return_value=response,
    ) as post:
        GeminiDenseEmbedder(
            model_name="gemini-embedding-001",
            api_key="test-key",
        ).embed_text("AirPure")

    assert post.call_args.kwargs["timeout"] == 90


def test_gemini_embedder_rejects_wrong_dimension():
    import pytest

    response = Mock(status_code=200)
    response.json.return_value = {"embedding": {"values": [0.5, 0.25]}}

    with patch("src.services.gemini_embedder.requests.post", return_value=response):
        with pytest.raises(ValueError, match="expected 768"):
            GeminiDenseEmbedder(api_key="test-key").embed_text("AirPure")


def test_gemini_http_error_does_not_expose_api_key():
    import pytest

    response = Mock(status_code=400)
    with patch(
        "src.services.gemini_embedder.requests.post",
        return_value=response,
    ):
        with pytest.raises(RuntimeError) as error:
            GeminiDenseEmbedder(api_key="test-secret").embed_text("AirPure")

    assert "HTTP 400" in str(error.value)
    assert "test-secret" not in str(error.value)
    assert "key=" not in str(error.value)


def test_gemini_embedder_fails_without_api_key():
    import pytest

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiDenseEmbedder(api_key="").embed_text("AirPure")


def test_gemini_embedder_raises_for_configured_model_http_error():
    import pytest

    response = Mock(status_code=404)
    with patch(
        "src.services.gemini_embedder.requests.post",
        return_value=response,
    ) as post:
        with pytest.raises(
            RuntimeError,
            match=r"models/gemini-embedding-001.*HTTP 404",
        ):
            GeminiDenseEmbedder(
                model_name="gemini-embedding-001",
                api_key="test-key",
            ).embed_text("AirPure")

    assert post.call_count == 1
    assert "models/gemini-embedding-001:embedContent" in post.call_args.args[0]
    assert post.call_args.kwargs["params"] == {"key": "test-key"}


def test_gemini_embedder_reports_read_timeout_without_exposing_key():
    import pytest
    import requests

    with patch(
        "src.services.gemini_embedder.requests.post",
        side_effect=requests.ReadTimeout,
    ):
        with pytest.raises(TimeoutError, match="timed out after 60s") as error:
            GeminiDenseEmbedder(api_key="test-secret").embed_text("AirPure")

    assert "test-secret" not in str(error.value)
