"""Run the complete RAG pipeline against the configured external services."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()


def _configured(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} chưa được cấu hình trong file .env.")
    return value


def _print_stage(name: str, value: Any) -> None:
    print(f"\n[{name}]")
    print(value)


def run(query: str) -> int:
    for name in ("GEMINI_API_KEY", "QDRANT_URL", "QDRANT_API_KEY"):
        _configured(name)

    from src.memory.semantic_rag.generator import RAGGenerator
    from src.memory.semantic_rag.hybrid_search import HybridSearchEngine
    from src.memory.semantic_rag.query_rewriter import rewrite
    from src.memory.semantic_rag.query_router import route
    from src.memory.semantic_rag.reranker import Reranker

    started = time.perf_counter()
    route_result = route(query)
    _print_stage("1. ROUTER", route_result)
    if route_result.get("early_response"):
        _print_stage("FINAL ANSWER", route_result["early_response"])
        return 0

    rewritten = rewrite(query, route_result["intent"])
    _print_stage("2. QUERY REWRITE", rewritten)
    engine = HybridSearchEngine()
    metadata = route_result.get("metadata", {})
    if route_result.get("collection") == "products":
        documents = engine.search_products(
            rewritten, top_k=5, category=metadata.get("category"),
            in_stock_only=metadata.get("in_stock_only", False),
            min_price=metadata.get("min_price"),
            max_price=metadata.get("max_price"),
        )
    else:
        documents = engine.search_policies(rewritten, top_k=5)
    _print_stage("3. GEMINI + QDRANT RETRIEVAL", documents)

    reranked = Reranker().rerank(rewritten, documents, top_n=5)
    _print_stage("4. LOCAL RERANKING", reranked)
    generator = RAGGenerator()
    answer = generator.generate(rewritten, reranked)
    _print_stage("5. GENERATOR ANSWER", answer)
    print("\n===== CHATBOT RESPONSE =====")
    print(answer)
    print("===== END CHATBOT RESPONSE =====")
    print(f"\nPipeline completed successfully in {time.perf_counter() - started:.2f}s.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "query", nargs="?",
        default="Mình muốn mua máy lọc không khí dưới 10 triệu còn hàng",
    )
    args = parser.parse_args()
    try:
        return run(args.query)
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
