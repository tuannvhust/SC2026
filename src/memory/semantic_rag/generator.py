"""Generate grounded answers with Gemini and Groq fallback."""

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

try:
    from google import genai
except ImportError:
    genai = None

load_dotenv()


SUPPORT_MESSAGE = (
    "Dạ hiện tại hệ thống tư vấn đang gặp sự cố kết nối với các dịch vụ "
    "AI. Anh/chị vui lòng thử lại sau hoặc liên hệ nhân viên hỗ trợ "
    "để được tư vấn trực tiếp ạ."
)


class RAGGenerator:
    def __init__(self, llm_client=None, model_name: Optional[str] = None):
        self.llm_client = llm_client
        self.model_name = model_name or os.getenv(
            "GEMINI_MODEL", "gemini-2.5-flash"
        )
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.client = (
            genai.Client(api_key=api_key)
            if api_key and genai is not None
            else None
        )
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.max_tokens = int(os.getenv("GENERATOR_MAX_TOKENS", "1000"))

    def build_prompt(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> str:
        context_texts = []
        for document in context_docs:
            sku = document.get("sku") or document.get("_id") or "N/A"
            text = document.get("embedding_text", "") or str(document)
            context_texts.append(f"[Nguồn SKU: {sku}]\n{text}")
        context_block = "\n\n".join(context_texts)
        return (
            "Bạn là Chuyên viên tư vấn bán hàng của SUDOTECH. Khi tư vấn sản phẩm, hãy tuân thủ cấu trúc sau:"
            "1. Lời chào ngắn gọn (1 câu).\n"
            "2. Tên sản phẩm nổi bật + Giá bán + Tình trạng kho hàng.\n"
            "3. Sử dụng Danh sách gạch đầu dòng (Bullet points) cho Thông số kỹ thuật chính (Màn hình, Chip, Pin, Camera).\n"
            "4. Các chương trình Khuyến mãi/Trả góp nổi bật.\n"
            "5. Câu hỏi gợi ý bước tiếp theo cho khách hàng.\n\n"
            "Luôn dùng định dạng Markdown chuẩn (**in đậm**, * gạch đầu dòng) và chèn icon cảm xúc phù hợp."
            "Dựa trên thông tin nguồn dưới đây, hãy trả lời câu hỏi khách hàng.\n"
            "- Không bịa giá, quà tặng hoặc khuyến mãi ngoài nguồn.\n"
            "- Luôn nêu SKU khi giới thiệu hoặc so sánh sản phẩm.\n\n"
            f"THÔNG TIN NGUỒN:\n{context_block}\n\n"
            f"CÂU HỎI KHÁCH HÀNG: {query}\n\n"
            "CÂU TRẢ LỜI CỦA BẠN:"
        )

    @staticmethod
    def _response_text(response: Any) -> Optional[str]:
        choices = getattr(response, "choices", [])
        if choices:
            text = getattr(choices[0].message, "content", None)
            if text:
                return text
        text = getattr(response, "text", None)
        if text:
            return text
        return None

    def generate(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> str:
        if not context_docs:
            return (
                "Dạ hiện tại em chưa tìm thấy thông tin sản phẩm hoặc chính "
                "sách phù hợp với yêu cầu của anh/chị ạ."
            )
        prompt = self.build_prompt(query, context_docs)
        if self.llm_client and hasattr(self.llm_client, "generate"):
            return self.llm_client.generate(prompt)

        failures: list[str] = []
        if self.client:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config={"max_output_tokens": self.max_tokens},
                )
                text = self._response_text(response)
                if text:
                    return text
                failures.append("Gemini trả về nội dung rỗng")
            except Exception as exc:
                failures.append(f"Gemini: {exc}")
        else:
            failures.append("Gemini chưa cấu hình GEMINI_API_KEY")

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            try:
                from groq import Groq

                response = Groq(api_key=groq_key).chat.completions.create(
                    model=self.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=self.max_tokens,
                )
                text = self._response_text(response)
                if text:
                    return text
                failures.append("Groq trả về nội dung rỗng")
            except Exception as exc:
                failures.append(f"Groq: {exc}")
        else:
            failures.append("Groq chưa cấu hình GROQ_API_KEY")

        print("[RAGGenerator] Fallback chain failed: " + " | ".join(failures))
        return SUPPORT_MESSAGE
