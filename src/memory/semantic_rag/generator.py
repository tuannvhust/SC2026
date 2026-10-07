"""Generate grounded answers with Gemini and Groq fallback."""

import logging
import os
from typing import Any, Dict, Iterator, List, Optional

from dotenv import load_dotenv

try:
    from google import genai
except ImportError:
    genai = None

load_dotenv()

logger = logging.getLogger(__name__)

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
        self.max_tokens = int(os.getenv("GENERATOR_MAX_TOKENS", "2048"))

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
            "Bạn là nhân viên tư vấn của SUDO SHOP. Dựa trên nguồn dưới đây, "
            "trả lời đúng trọng tâm bằng tiếng Việt.\n"
            "- Không bịa giá, quà tặng hoặc khuyến mãi ngoài nguồn.\n"
            "- Khi tư vấn sản phẩm, nêu tên, SKU, giá và tồn kho nếu nguồn có.\n"
            "- Chỉ nêu thuộc tính và phiên bản có trong nguồn; không giả định "
            "mọi sản phẩm đều có cùng loại thông số.\n"
            "- Không khẳng định có trả góp, trade-in hoặc khuyến mãi nếu nguồn "
            "không ghi nhận.\n"
            "- Dùng Markdown dễ đọc, không cần thêm lời chào hoặc mục không "
            "liên quan khi khách chỉ hỏi thông tin cụ thể.\n\n"
            f"THÔNG TIN NGUỒN:\n{context_block}\n\n"
            f"CÂU HỎI KHÁCH HÀNG: {query}\n\n"
            "CÂU TRẢ LỜI CỦA BẠN:"
        )

    def generate(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> str:
        return "".join(self.generate_stream(query, context_docs))

    def generate_stream(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> Iterator[str]:
        if not context_docs:
            yield (
                "Dạ hiện tại em chưa tìm thấy thông tin sản phẩm hoặc chính "
                "sách phù hợp với yêu cầu của anh/chị ạ."
            )
            return

        prompt = self.build_prompt(query, context_docs)
        if self.llm_client:
            stream = getattr(self.llm_client, "generate_stream", None)
            if stream:
                yield from stream(prompt)
                return
            generate = getattr(self.llm_client, "generate", None)
            if generate:
                yield generate(prompt)
                return

        failures: list[str] = []
        if self.client:
            emitted = False
            try:
                chat = self.client.chats.create(
                    model=self.model_name,
                    config={
                        "temperature": 0.3,
                        "max_output_tokens": self.max_tokens,
                    },
                )
                for chunk in chat.send_message_stream(prompt):
                    finish_reason = self._gemini_finish_reason(chunk)
                    if finish_reason:
                        logger.debug("Gemini finish_reason=%s", finish_reason)
                    if finish_reason == "MAX_TOKENS":
                        logger.warning(
                            "Gemini response truncated at max_output_tokens"
                        )
                        raise RuntimeError(
                            "Gemini output truncated (finish_reason=MAX_TOKENS)"
                        )
                    text = getattr(chunk, "text", None)
                    if text:
                        emitted = True
                        yield text
                if emitted:
                    return
                failures.append("Gemini trả về nội dung rỗng")
            except Exception as exc:
                if emitted:
                    raise
                failures.append(f"Gemini: {exc}")
        else:
            failures.append("Gemini chưa cấu hình GEMINI_API_KEY")

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            emitted = False
            try:
                from groq import Groq

                response_stream = Groq(api_key=groq_key).chat.completions.create(
                    model=self.groq_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=self.max_tokens,
                    stream=True,
                )
                for chunk in response_stream:
                    choices = getattr(chunk, "choices", [])
                    if not choices:
                        continue
                    choice = choices[0]
                    finish_reason = getattr(choice, "finish_reason", None)
                    if finish_reason == "length":
                        logger.warning("Groq response truncated at max_tokens")
                        raise RuntimeError(
                            "Groq output truncated (finish_reason=length)"
                        )
                    text = getattr(getattr(choice, "delta", None), "content", None)
                    if text:
                        emitted = True
                        yield text
                if emitted:
                    return
                failures.append("Groq trả về nội dung rỗng")
            except Exception as exc:
                if emitted:
                    raise
                failures.append(f"Groq: {exc}")
        else:
            failures.append("Groq chưa cấu hình GROQ_API_KEY")

        logger.error("RAG generator fallback chain failed: %s", " | ".join(failures))
        yield SUPPORT_MESSAGE

    @staticmethod
    def _gemini_finish_reason(response: Any) -> Optional[str]:
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return None
        reason = getattr(candidates[0], "finish_reason", None)
        if reason is None:
            return None
        return str(getattr(reason, "name", reason)).rsplit(".", 1)[-1].upper()
