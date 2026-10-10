from unittest.mock import Mock, patch

from src.memory.semantic_rag.reranker import Reranker


def test_reranker_uses_hugging_face_scores():
    response = Mock(ok=True)
    response.json.return_value = [0.1, 0.9]

    documents = [
        {"embedding_text": "MacBook", "sku": "macbook"},
        {"embedding_text": "Samsung Galaxy", "sku": "samsung"},
    ]

    with patch(
        "src.memory.semantic_rag.reranker.requests.post",
        return_value=response,
    ) as post:
        result = Reranker(
            api_url="https://example.test/reranker",
            token="test-token",
        ).rerank("điện thoại Samsung", documents, top_n=1)

    assert result == [{**documents[1], "rerank_score": 0.9}]
    post.assert_called_once()
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_reranker_extracts_nested_label_scores():
    scores = Reranker(token="test-token")._extract_scores(
        [
            [
                {"label": "LABEL_0", "score": 0.1},
                {"label": "LABEL_1", "score": 0.9},
            ],
            [
                {"label": "LABEL_0", "score": 0.8},
                {"label": "LABEL_1", "score": 0.2},
            ],
        ],
        expected_count=2,
    )

    assert scores == [0.9, 0.2]
