import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.memory.semantic_rag.generator import RAGGenerator


class FakeLLM:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "Tư vấn Samsung Galaxy A55, SKU-A55."


def test_generator_returns_safe_empty_context_response():
    response = RAGGenerator().generate("Samsung", [])

    assert "chưa tìm thấy" in response


def test_generator_includes_source_sku_in_prompt():
    prompt = RAGGenerator().build_prompt(
        "Samsung",
        [{"sku": "SKU-A55", "embedding_text": "Samsung Galaxy A55"}],
    )

    assert "SKU-A55" in prompt
    assert "Samsung Galaxy A55" in prompt


def test_generator_returns_llm_answer_from_retrieved_context():
    llm = FakeLLM()
    generator = RAGGenerator(llm_client=llm)

    response = generator.generate(
        "Mình muốn mua Samsung dưới 10 triệu",
        [
            {
                "sku": "SKU-A55",
                "embedding_text": "Samsung Galaxy A55 giá 9.490.000đ, còn hàng.",
            }
        ],
    )

    assert response == "Tư vấn Samsung Galaxy A55, SKU-A55."
    assert len(llm.prompts) == 1
    assert "SKU-A55" in llm.prompts[0]


def test_generator_falls_back_from_gemini_to_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-test")
    generator = RAGGenerator()
    generator.client = Mock()
    generator.client.models.generate_content.side_effect = RuntimeError(
        "Gemini unavailable"
    )
    groq_response = Mock()
    groq_response.choices = [Mock(message=Mock(content="Câu trả lời từ Groq."))]
    fake_groq = SimpleNamespace(Groq=Mock(return_value=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=Mock(return_value=groq_response)
        ))
    )))
    with patch.dict(sys.modules, {"groq": fake_groq}):
        response = generator.generate("Samsung", [{"sku": "SKU-A55"}])

    assert response == "Câu trả lời từ Groq."
    fake_groq.Groq.assert_called_once_with(api_key="groq-test")
    assert fake_groq.Groq.return_value.chat.completions.create.call_args.kwargs[
        "max_tokens"
    ] == 1000


def test_generator_returns_support_message_when_all_fail(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    generator = RAGGenerator()
    generator.client = Mock()
    generator.client.models.generate_content.side_effect = RuntimeError(
        "Gemini unavailable"
    )
    response = generator.generate("Samsung", [{"sku": "SKU-A55"}])
    assert "liên hệ nhân viên hỗ trợ" in response
