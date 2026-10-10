'''src/memory/semantic_rag/query_rewriter.py
Simple query rewriter module.
Currently performs no transformation (identity) as per user request to avoid HyDE.
Can be extended later with deterministic synonym expansion if needed.
'''


def rewrite(query: str, intent: str) -> str:
    """Rewrite the query based on intent.

    For now, the rewriter is a no‑op and simply returns the original query.
    This satisfies the requirement of not using HyDE.
    """
    # Placeholder for future expansion (e.g., synonym injection)
    return query
