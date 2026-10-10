from unittest.mock import Mock, patch

from src.services.gemini_embedder import GeminiDenseEmbedder


def test_gemini_embedder_uses_configured_model_and_normalizes_dimension():
    response = Mock(status_code=200)
    response.json.return_value = {"embedding": {"values": [0.5, 0.25]}}

    with patch("src.services.gemini_embedder.requests.post", return_value=response) as post:
        values = GeminiDenseEmbedder(
            model_name="models/test-embedding",
            api_key="test-key",
        ).embed_text("Samsung")

    assert len(values) == 768
    assert values[:2] == [0.5, 0.25]
    assert "models/test-embedding:embedContent" in post.call_args.args[0]


def test_gemini_embedder_falls_back_to_zero_vector_without_key():
    values = GeminiDenseEmbedder(api_key="").embed_text("Samsung")

    assert values == [0.0] * 768
