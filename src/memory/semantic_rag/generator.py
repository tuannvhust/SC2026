"""
src/memory/semantic_rag/generator.py
Sinh câu trả lời từ context truy xuất được, luôn kèm trích dẫn SKU nguồn.
Tuân thủ nguyên tắc: không để LLM tự suy đoán giá/khuyến mãi ngoài context.
"""

from typing import List, Dict, Any, Optional


class RAGGenerator:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def build_prompt(self, query: str, context_docs: List[Dict[str, Any]]) -> str:
        """
        Xây dựng prompt với context đầy đủ và yêu cầu trích dẫn nguồn SKU.
        """
        context_texts = []
        for d in context_docs:
            sku = d.get("sku") or d.get("_id")
            text = d.get("embedding_text", "")
            context_texts.append(f"[Nguồn: {sku}]\n{text}")

        context_block = "\n\n".join(context_texts)
        prompt = (
            "Bạn là trợ lý tư vấn bán hàng chuyên nghiệp cho cửa hàng điện máy.\n"
            "Dựa trên các thông tin sản phẩm và chính sách dưới đây, hãy trả lời câu hỏi của khách hàng.\n"
            "LƯU Ý QUAN TRỌNG:\n"
            "- Tuyệt đối không tự bịa giá bán, quà tặng hoặc khuyến mãi không có trong nguồn.\n"
            "- Luôn nêu rõ mã SKU nguồn khi giới thiệu hoặc so sánh sản phẩm.\n\n"
            f"THÔNG TIN NGUỒN:\n{context_block}\n\n"
            f"CÂU HỎI KHÁCH HÀNG: {query}\n\n"
            "CÂU TRẢ LỜI CỦA BẠN:"
        )
        return prompt

    def generate(self, query: str, context_docs: List[Dict[str, Any]]) -> str:
        if not context_docs:
            return "Dạ hiện tại em chưa tìm thấy thông tin sản phẩm hoặc chính sách phù hợp với yêu cầu của anh/chị ạ."

        prompt = self.build_prompt(query, context_docs)
        if self.llm_client:
            return self.llm_client.generate(prompt)
        return f"[Draft response based on {len(context_docs)} documents]"

