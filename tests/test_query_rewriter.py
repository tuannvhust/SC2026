from src.memory.semantic_rag.query_rewriter import rewrite


def test_rewriter_is_deterministic_identity():
    query = "Mình muốn mua điện thoại Samsung"

    assert rewrite(query, "product") == query
