from unittest.mock import Mock, patch

from src.memory.semantic_rag.reranker import Reranker


def test_reranker_uses_local_cross_encoder_scores():
    documents = [
        {"embedding_text": "Máy lọc không khí AirPure X", "sku": "SKU-AP-X"},
        {"embedding_text": "Giày chạy bộ RunLite 1", "sku": "SKU-SN-RUN1"},
    ]
    model = Mock()
    model.predict.return_value = [0.1, 0.9]

    with patch(
        "sentence_transformers.CrossEncoder",
        return_value=model,
    ) as cross_encoder:
        result = Reranker().rerank("Giày RunLite", documents, top_n=1)

    assert result == [{**documents[1], "rerank_score": 0.9}]
    cross_encoder.assert_called_once_with(
        "BAAI/bge-reranker-base",
        device="cpu",
        automodel_args={"local_files_only": True},
    )
    model.predict.assert_called_once_with(
        [
            ["Giày RunLite", "Máy lọc không khí AirPure X"],
            ["Giày RunLite", "Giày chạy bộ RunLite 1"],
        ]
    )


def test_reranker_does_not_load_model_for_empty_documents():
    reranker = Reranker()

    assert reranker.rerank("query", []) == []
    assert reranker._model is None


def test_reranker_reuses_loaded_model():
    documents = [{"embedding_text": "text"}]
    model = Mock()
    model.predict.return_value = [0.5]

    with patch(
        "sentence_transformers.CrossEncoder",
        return_value=model,
    ) as cross_encoder:
        reranker = Reranker()
        reranker.rerank("query", documents)
        reranker.rerank("query", documents)

    cross_encoder.assert_called_once_with(
        "BAAI/bge-reranker-base",
        device="cpu",
        automodel_args={"local_files_only": True},
    )


def test_reranker_warmup_loads_model_and_runs_prediction():
    model = Mock()
    model.predict.return_value = [0.5]

    with patch(
        "sentence_transformers.CrossEncoder",
        return_value=model,
    ) as cross_encoder:
        reranker = Reranker()
        reranker.warmup()

    cross_encoder.assert_called_once_with(
        "BAAI/bge-reranker-base",
        device="cpu",
        automodel_args={"local_files_only": True},
    )
    model.predict.assert_called_once_with([["warmup", "warmup"]])
