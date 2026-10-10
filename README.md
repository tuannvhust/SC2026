# SC2026 - Hệ Thống Trợ Lý Giọng Nói & Telesales AI

Hệ thống trợ lý AI hội thoại phục vụ tự động hóa quy trình telesales và tư vấn khách hàng, với khả năng bám sát dữ liệu thực tế (grounding), lưu trữ bộ nhớ khách hàng dài hạn và thiết lập guardrail ngăn chặn việc bịa đặt thông tin (hallucination).

## Cấu trúc Repository

```text
SC2026/
├── .gitignore
├── .env.example
├── requirements.txt
├── README.md
│
└── langgraph_agent/              # Module LangGraph Telesales Agent (M1)
    ├── README.md                 # Tài liệu về agent & hướng dẫn chạy
    ├── src/                      # Source code
    │   ├── __init__.py
    │   ├── state.py              # Định nghĩa schema CallState
    │   ├── memory.py             # Bộ nhớ SQLite (quản lý slot profile & episodic)
    │   ├── tools.py              # Mock catalog, CRM lookup và công cụ tạo đơn hàng
    │   ├── prompts.py            # System prompt & định dạng prompt
    │   ├── llm.py                # Tích hợp Gemini API & bộ giả lập offline
    │   ├── guardrails.py         # Kiểm tra guardrail giá tiền
    │   ├── nodes.py              # Các node thực thi trong graph
    │   ├── edges.py              # Các conditional edge điều hướng luồng
    │   └── graph.py              # Xây dựng và biên dịch LangGraph
    ├── tests/
    │   └── test_graph.py         # Test suite viết bằng pytest
    └── examples/
        └── run_graph.py          # Script chạy thử nghiệm hội thoại đa lượt
```

## Bắt đầu nhanh (Quick Start)

### 1. Cài đặt thư viện dependencies

```bash
pip install -r requirements.txt
```

### 2. Cấu hình biến môi trường

Sao chép `.env.example` thành `.env` nếu bạn muốn chạy cùng LLM thật:

```bash
cp .env.example .env
```

_(Lưu ý: Nếu không cấu hình `GEMINI_API_KEY` (hoặc `GOOGLE_API_KEY`), agent sẽ tự động kích hoạt chế độ stand-in dựa trên luật/regex để chạy offline, cho phép test và kiểm thử toàn bộ luồng mà không tốn chi phí API)._

### 3. Chạy demo

```bash
python langgraph_agent/examples/run_graph.py
```

### 4. Chạy bộ kiểm thử (test suite)

```bash
pytest langgraph_agent/tests
```

Để tìm hiểu chi tiết hơn về kiến trúc graph, luồng điều hướng giữa các node và hướng dẫn tích hợp RAG (M2), vui lòng xem tại [`langgraph_agent/README.md`](langgraph_agent/README.md).

Graph hiện thực gồm input guardrail và nhánh từ chối, agent loop có tool/RAG qua bước tổng hợp kết quả, output guardrail với retry/handoff, cùng `persist_call` khi kết thúc cuộc gọi. Chi tiết và cách đánh dấu kết thúc cuộc gọi nằm trong tài liệu module.
