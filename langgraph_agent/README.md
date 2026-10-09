# Triển khai LangGraph

## 1. Tổng quan

Module này triển khai một agent telesales AI hội thoại xây dựng trên nền tảng **LangGraph**. Hệ thống quản lý các cuộc gọi tư vấn khách hàng bằng tiếng Việt với yêu cầu nghiêm ngặt về tính chính xác của dữ liệu, bộ nhớ dài hạn và các lớp guardrail an toàn.

### Vấn đề giải quyết

Hội thoại telesales đòi hỏi thông tin sản phẩm theo thời gian thực (giá, tồn kho, khuyến mãi), bộ nhớ xuyên suốt giữa các cuộc gọi (như diện tích phòng, ngân sách, rào cản tâm lý của khách), và tuyệt đối không được báo sai giá. Agent đảm nhiệm:

- **Ngăn chặn hallucination giá tiền**: Mọi mức giá hay khuyến mãi báo cho khách đều bắt buộc phải lấy từ kết quả thực thi tool truy vấn catalog trong lượt đó.
- **Bộ nhớ khách hàng xuyên cuộc gọi**: Nhận diện khách hàng quay lại qua hàm băm số điện thoại (bảo vệ PII) và tiếp nối ngữ cảnh đã tư vấn trước đó mà không hỏi lại các thông tin đã biết.
- **Xử lý sự cố & chuyển máy**: Tự động chuyển máy cho nhân viên chuyên trách khi gặp câu hỏi ngoài phạm vi, tool bị timeout hoặc guardrail vi phạm nhiều lần; đồng thời ghi nhận vào bảng `knowledge_gaps` để đội ngũ hoàn thiện tri thức.
- **Khả năng mở rộng tích hợp RAG**: Cung cấp sẵn một node độc lập (`retrieve_context`) sẵn sàng kết nối trực tiếp với pipeline RAG của nhóm trong Milestone 2.

### Các thành phần LangGraph sử dụng

- **`StateGraph`**: Quản lý quy trình và điều phối chuyển trạng thái giữa các node.
- **`CallState` (TypedDict)**: Schema lưu trạng thái cuộc gọi, sử dụng `operator.add` để tích lũy lịch sử hội thoại (`messages`) qua các lượt.
- **`MemorySaver`**: Quản lý checkpoint trong bộ nhớ cho các lượt thoại trong cùng một phiên gọi (`thread_id = call_id`).
- **Nodes**: Các đơn vị xử lý độc lập cho việc định danh CRM, tạo Call Brief, chuẩn hóa ASR/teencode, truy xuất ngữ cảnh, lập kế hoạch, gọi tool, kiểm tra guardrail, chuyển máy, lưu lượt và xuất trace.
- **Conditional Edges**: Điều hướng rẽ nhánh động dựa trên hành động của planner, kết quả tool, trạng thái guardrail và số lần retry.

---

## 2. Kiến trúc Graph

```mermaid
flowchart TB
 subgraph INPUT["1. INPUT & SESSION CONTINUITY"]
        IG{{"<b>input_guardrail</b><br>Kiểm tra đầu vào<br>"}}
        N["<b>normalize_input</b><br>Chuẩn hóa đầu vào<br>"]
        S["<b>resolve_identity</b><br>Xác định khách hàng theo customer_id<br>"]
        B["<b>build_call_brief<br></b>Tạo call brief nếu là khách cũ"]
        IM["Từ chối trả lời"]
  end
 subgraph TOOL["THỰC THI TOOL"]
        T["<b>call_tool</b><br>crm.get_customer<br>catalog.search<br>order.create<br>...."]
        RAG["<b>RAG Tool</b><br>policy_kb.search<br>"]
        RE["<b>collect_tool_results</b><br>Tổng hợp kết quả"]
  end
 subgraph AGENT["2. AGENT LOOP"]
        P{{"<b>plan_step</b><br>answer / clarify / tool / handoff / RAG"}}
        TOOL
  end
 subgraph SAFETY["3. OUTPUT SAFETY"]
        OG{{"<b>output_guardrail<br></b>Kiểm tra giá, KM khớp với tool_result<br>"}}
        R["Thử lại"]
        H["<b>handoff_to_human</b><br>Tạo handoff brief, chuyển máy cho nhân viên"]
  end
 subgraph MEMORY["4. MEMORY"]
        WM["<b>persist_turn</b><br>Lưu hội thoại<br>Working Memory/Event Log"]
        LM["<b>persist_call</b><br>Bộ nhớ cuộc gọi<br>Trích xuất → Kiểm tra → Lưu"]
  end
    START(["<b>START<br></b>Khách gửi tin nhắn / cuộc gọi"]) --> IG
    IG -- Không hợp lệ /<br>ngoài phạm vi --> IM
    IM --> WM
    IG -- Hợp lệ --> N
    N --> S
    S --> B
    B --> P
    P -- trả lời / làm rõ --> OG
    P -- gọi tool --> T
    T --> RE
    RAG --> RE
    P -- không trả lời được<br>(ngoài phạm vi tài liệu) --> H
    P -- cần thông tin từ KB --> RAG
    RE --> P
    OG -- đạt --> WM
    OG -- không đạt --> R
    R -- còn lượt thử lại --> P
    R -- hết lượt thử lại --> H
    H --> WM
    WM -- input không hợp lệ --> END(["<b>END</b><br>Chờ lượt tiếp"])
    WM -. cuộc gọi kết thúc .-> LM
    LM --> END

    H@{ shape: rect}
    style IG fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style RAG fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style TOOL fill:#fff7fd,stroke:#c2620a,stroke-width:2px
    style OG fill:#fce4ec,stroke:#ad1457,stroke-width:2px
    style H fill:#ffebee,stroke:#b71c1c,stroke-width:2px
    style INPUT fill:#eef2ff,stroke:#3b4a9e,stroke-width:2px
    style AGENT fill:#fff7ed,stroke:#c2620a,stroke-width:2px
    style SAFETY fill:#fdecea,stroke:#b3261e,stroke-width:2px
    style MEMORY fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
```

---

## 3. Cấu trúc thư mục

```text
langgraph_agent/
├── README.md                 # Tài liệu hướng dẫn
├── src/                      # Source code
│   ├── __init__.py           # Export các hàm và class public (build_graph, handle_customer_turn, ...)
│   ├── state.py              # Định nghĩa TypedDict CallState
│   ├── memory.py             # Quản lý SQLite database (profile slots, episodic summaries, CRM)
│   ├── tools.py              # Tool tìm kiếm catalog, tạo đơn hàng, tra cứu CRM & registry TOOLS
│   ├── prompts.py            # System prompt cho telesale & hàm format prompt
│   ├── llm.py                # Gọi Anthropic API & bộ stand-in chạy offline bằng rule
│   ├── guardrails.py         # Regex bóc tách số tiền & hàm kiểm tra đối soát với kết quả tool
│   ├── nodes.py              # Định nghĩa các node thực thi trong graph
│   ├── edges.py              # Các hàm điều hướng conditional edge
│   └── graph.py              # Khởi tạo StateGraph, biên dịch và các hàm public API
├── tests/
│   └── test_graph.py         # Bộ test suite đầy đủ (pytest)
└── examples/
    └── run_graph.py          # Script chạy thử nghiệm mẫu một kịch bản hội thoại
```

---

## 4. Cài đặt và Chạy thử

### Điều kiện tiên quyết (Prerequisites)

- Python 3.10 trở lên
- Cài đặt các thư viện cần thiết:
  ```bash
  pip install -r requirements.txt
  ```

### Cấu hình biến môi trường

Sao chép `.env.example` thành `.env` và điền các giá trị mong muốn:

```bash
cp .env.example .env
```

Các biến môi trường chính:

- `ANTHROPIC_API_KEY`: API key của Anthropic. Nếu để trống, hệ thống sẽ tự động chuyển sang chế độ stand-in offline phục vụ kiểm thử.
- `HARNESS_MODEL`: Model sử dụng (mặc định: `claude-sonnet-4-6`).
- `HARNESS_DB`: Đường dẫn file SQLite database (mặc định: `harness_memory.db`).

### Chạy kịch bản ví dụ

Để chạy thử kịch bản mô phỏng khách hàng mới và khách hàng quay lại:

```bash
python langgraph_agent/examples/run_graph.py
```

### Chạy kiểm thử tự động

Chạy bộ test suite với `pytest`:

```bash
pytest langgraph_agent/tests
```

Tất cả 7 kịch bản kiểm thử (khách hàng mới, khách hàng cũ tiếp nối thông tin, cập nhật hủy slot cũ khi khách đổi ý, guardrail chặn giá ảo và retry thành công, câu hỏi lạ chuyển máy & ghi nhận gap, timeout tool xử lý êm đẹp, regex nhận diện tiền) đều chạy offline mà không phụ thuộc vào API key bên ngoài.

---#

## 5. Chạy trace theo contract BTC

Agent đọc dữ liệu từ `data/catalog/` và dùng đúng tên tool trong
`data/schemas/tools.schema.json`. Ngày gọi được truyền vào mọi tool có tham số
`on`; không dùng ngày hệ thống.

```bash
python langgraph_agent/run_eval.py --scenarios data/test_set/public_sample --config full --out full.jsonl
python data/eval/reference_eval.py --scenarios data/test_set/public_sample --trace full.jsonl
```

Thay `full` bằng `baseline_no_memory` để chạy cấu hình không dùng memory dài hạn.
Trace chứa `questions`, `claims`, `facts_used`, `memory_writes`, tool calls theo
tên BTC và latency fields.
