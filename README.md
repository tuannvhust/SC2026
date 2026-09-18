# SC2026

# SUDO CODE 2026 — Harness Agent cho Call Center Telesale (Vòng 1)

Harness Agent hỗ trợ telesale e-commerce: ngữ cảnh liên tục xuyên phiên/kênh,
tự đánh giá và cải tiến theo thời gian (không fine-tune model).

## Cấu trúc thư mục

```
.
├── data/
│   ├── raw/
│   │   ├── audio/           # file ghi âm cuộc gọi (thật hoặc TTS)
│   │   ├── transcripts/     # transcript hội thoại dạng text
│   │   └── chat/            # log chat (Zalo/Fanpage/app)
│   ├── processed/           # output đã qua ASR + chuẩn hóa + trích xuất
│   ├── catalog/             # catalog sản phẩm + chính sách (catalog.json)
│   └── test_scenarios/      # bộ test đa phiên (Phụ lục B format)
│
├── src/
│   ├── asr/                 # Whisper/PhoWhisper, chuẩn hóa số (ITN)
│   ├── nlp_extraction/      # trích xuất có cấu trúc: intent, entity, slot
│   ├── models/               # Pydantic schema: CallTurn, CallSummary, Product, TestScenario
│   ├── services/              # client wrapper dùng lại nhiều nơi: llm_client, vector_store, profile_store
│   ├── retrieval/
│   │   └── query_router.py   # phân loại lượt thoại: hỏi sản phẩm / đơn hàng / phản đối / chitchat -> chọn tool
│   ├── memory/
│   │   ├── working/         # ngữ cảnh lượt thoại hiện tại
│   │   ├── episodic/        # tóm tắt từng cuộc gọi (giữ source_call_id để truy vết)
│   │   ├── profile/         # sự thật bền vững về khách
│   │   └── semantic_rag/    # RAG trên catalog/chính sách
│   │       ├── ingestion.py    # catalog.json -> document (text + metadata) để embed
│   │       ├── retriever.py    # tìm sản phẩm liên quan từ vector DB (search, get_by_sku)
│   │       ├── reranker.py     # rerank lại top-k kết quả (M2, để trống ở M1)
│   │       └── generator.py    # sinh câu trả lời từ context, kèm trích dẫn SKU nguồn
│   ├── harness/             # vòng lặp perceive→resolve→retrieve→plan→act→observe→persist
│   ├── mcp_servers/
│   │   ├── mcp_memory/      # MCP server đọc/ghi bộ nhớ khách hàng (bắt buộc)
│   │   └── mcp_catalog/     # MCP server tra catalog/giá/KM
│   ├── tools/                # crm.get_customer, catalog.search, order.create...
│   │                          #   (giá/chỉ số PHẢI tính bằng Python thuần, không để LLM tự suy đoán)
│   ├── eval/                 # script tính RQR, CCR, TSR, HR, WER/CER + baseline
│   ├── improvement_loop/     # Knowledge Gap Loop / Exemplar Bank
│   └── api/
│       └── routers/          # chat.py, calls.py, health.py — tách theo domain, không gộp 1 file
│
├── frontend/                 # Streamlit/web UI: chat + Call Brief + timeline
├── docs/
│   ├── architecture/         # sơ đồ hệ thống, thiết kế bộ nhớ
│   └── decisions/            # ghi lại các quyết định thiết kế + lý do
├── scripts/                  # script sinh dataset, seed catalog, chạy eval
├── notebooks/                # thử nghiệm nhanh (EDA, thử prompt...)
└── tests/                    # unit test cho từng module

```

## Bắt đầu

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # điền API key LLM
python scripts/seed_catalog.py   # nạp data/catalog/catalog.json vào vector DB
python -m src.api.main           # chạy backend
```

## `semantic_rag/` — tầng Semantic/KB memory

Đây là RAG trên `data/catalog/catalog.json` (giá, KM còn hiệu lực, chính
sách đổi trả/ship) — 1 trong 4 tầng bộ nhớ của đề bài (Working/Episodic/
Profile là M1 bắt buộc, Semantic/RAG là M2 nhưng cần làm sớm vì đây là
nguồn sự thật để agent không tự bịa giá/khuyến mãi — tránh Hallucination
Rate). 4 file trong đó chia theo luồng xử lý:

1. `ingestion.py` chuẩn hoá catalog thành document có thể embed.
2. `retriever.py` tìm các document liên quan tới câu hỏi khách.
3. `reranker.py` (tuỳ chọn) sắp xếp lại kết quả cho chính xác hơn.
4. `generator.py` dùng kết quả đó để sinh câu trả lời, luôn kèm SKU nguồn.

Tách 4 bước riêng để mỗi phần test được độc lập (ví dụ đo Recall@k chỉ ở
bước retriever, không lẫn với chất lượng câu trả lời của generator).

## Quy ước khi mở rộng

- **Không để LLM tự tính/tự nhớ số liệu.** Giá, tồn kho, KM còn hiệu lực luôn
  phải đi qua `tools/` hoặc `retrieval/`, không được LLM tự suy đoán trong prompt.
- **Mọi fact ghi vào Episodic/Profile phải giữ nguồn gốc** (`source_call_id`,
  `extracted_at`) — để truy vết khi cần xóa hoặc phát hiện memory poisoning.
- **`services/` chỉ chứa client wrapper thuần** (gọi LLM, đọc/ghi vector DB,
  đọc/ghi profile store) — không chứa business logic. Logic nghiệp vụ (route,
  quyết định ghi gì vào bộ nhớ) nằm ở `harness/` và `retrieval/`.
- **Không để script thử nghiệm rải ở thư mục gốc** — mọi test vào `tests/`,
  mọi thử nghiệm nhanh vào `notebooks/`.