"""Run the complete RAG pipeline against the configured external services."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

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
    if route_result.get("status") == "error":
        print("\nRouter không thể phân tích câu hỏi; dừng pipeline.", file=sys.stderr)
        return 1
    if route_result.get("early_response"):
        _print_stage("FINAL ANSWER", route_result["early_response"])
        return 0

    rewritten = rewrite(query, route_result["intent"])
    _print_stage("2. QUERY REWRITE", rewritten)
    engine = HybridSearchEngine()
    metadata = route_result.get("metadata", {})
    if route_result.get("collection") == "products":
        documents = engine.search_products(
            rewritten,
            top_k=30 if any(
                (
                    metadata.get("in_stock_only", False),
                    metadata.get("min_price") is not None,
                    metadata.get("max_price") is not None,
                    metadata.get("room_area_m2") is not None,
                )
            ) else 5,
            category=metadata.get("category"),
        )
        room_area = metadata.get("room_area_m2")
        if room_area is not None:
            from src.memory.semantic_rag.orchestrator import _supports_room_area

            documents = [
                document
                for document in documents
                if _supports_room_area(document, float(room_area))
            ]
        if (
            metadata.get("in_stock_only", False)
            or metadata.get("min_price") is not None
            or metadata.get("max_price") is not None
        ):
            from src.tools.tool_repository import filter_catalog_candidates

            documents = filter_catalog_candidates(
                documents,
                min_price_vnd=metadata.get("min_price"),
                max_price_vnd=metadata.get("max_price"),
                in_stock_only=metadata.get("in_stock_only", False),
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
        default="Tìm cho mình máy lọc không khí phòng 30m2 dưới 5 triệu",
    )
    args = parser.parse_args()
    try:
        return run(args.query)
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
