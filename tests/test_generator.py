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
    monkeypatch.setenv("GENERATOR_MAX_TOKENS", "2048")
    generator = RAGGenerator()
    generator.client = Mock()
    generator.client.chats.create.side_effect = RuntimeError("Gemini unavailable")
    groq_chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content="Câu trả lời từ Groq."),
                finish_reason=None,
            )]
        ),
    ]
    fake_groq = SimpleNamespace(Groq=Mock(return_value=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=Mock(return_value=iter(groq_chunks))
        ))
    )))
    with patch.dict(sys.modules, {"groq": fake_groq}):
        response = generator.generate("Samsung", [{"sku": "SKU-A55"}])

    assert response == "Câu trả lời từ Groq."
    fake_groq.Groq.assert_called_once_with(api_key="groq-test")
    assert fake_groq.Groq.return_value.chat.completions.create.call_args.kwargs[
        "max_tokens"
    ] == 2048
    assert fake_groq.Groq.return_value.chat.completions.create.call_args.kwargs[
        "stream"
    ] is True


def test_generator_falls_back_when_gemini_hits_output_limit(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-test")
    monkeypatch.setenv("GENERATOR_MAX_TOKENS", "2048")
    generator = RAGGenerator()
    generator.client = Mock()
    generator.client.chats.create.return_value.send_message_stream.return_value = iter(
        [
            SimpleNamespace(
                text="Dựa trên nhu",
                candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
            )
        ]
    )
    groq_chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(content="Câu trả lời hoàn chỉnh."),
                finish_reason=None,
            )]
        ),
    ]
    fake_groq = SimpleNamespace(Groq=Mock(return_value=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=Mock(return_value=iter(groq_chunks))
        ))
    )))

    with patch.dict(sys.modules, {"groq": fake_groq}):
        response = generator.generate("Samsung", [{"sku": "SKU-A55"}])

    assert response == "Câu trả lời hoàn chỉnh."
    generator.client.chats.create.assert_called_once_with(
        model=generator.model_name,
        config={
            "temperature": 0.3,
            "max_output_tokens": 2048,
        },
    )
    fake_groq.Groq.return_value.chat.completions.create.assert_called_once()


def test_generator_returns_support_message_when_all_fail(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    generator = RAGGenerator()
    generator.client = Mock()
    generator.client.chats.create.side_effect = RuntimeError("Gemini unavailable")
    response = generator.generate("Samsung", [{"sku": "SKU-A55"}])
    assert "liên hệ nhân viên hỗ trợ" in response


def test_generator_streams_gemini_chat_chunks():
    generator = RAGGenerator()
    generator.client = Mock()
    generator.client.chats.create.return_value.send_message_stream.return_value = iter(
        [
            SimpleNamespace(text="Xin chào "),
            SimpleNamespace(text="anh/chị!"),
        ]
    )

    chunks = list(generator.generate_stream("Samsung", [{"sku": "SKU-A55"}]))

    assert chunks == ["Xin chào ", "anh/chị!"]
    generator.client.chats.create.return_value.send_message_stream.assert_called_once()
