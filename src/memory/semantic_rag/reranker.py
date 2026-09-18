"""
src/memory/semantic_rag/reranker.py
Rerank lại top-k kết quả từ Retriever (M2 - Milestone 2).
Ở giai đoạn M1, trả về nguyên trạng danh sách tài liệu hoặc sắp xếp theo score có sẵn.
"""

from typing import List, Dict, Any


class Reranker:
    def __init__(self, model_name: str = None):
        self.model_name = model_name

    def rerank(self, query: str, documents: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
        """
        M2: Dùng Cross-Encoder (như bge-reranker) để chấm điểm lại mức độ phù hợp.
        M1: Trả về top_n tài liệu đầu tiên.
        """
        return documents[:top_n]

