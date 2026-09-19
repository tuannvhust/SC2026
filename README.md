```markdown
# SUDO CODE 2026 — Harness Agent cho Call Center Telesale

Harness Agent hỗ trợ telesale e-commerce: ngữ cảnh liên tục xuyên phiên/kênh, tự đánh giá và cải tiến theo thời gian (không fine-tune model).

## Cấu trúc thư mục

```
.
├── data/
│   ├── raw/              # audio, transcripts, chat logs
│   ├── processed/        # output ASR + chuẩn hóa
│   ├── catalog/          # catalog.json
│   └── test_scenarios/
├── src/
│   ├── asr/
│   ├── nlp_extraction/
│   ├── models/           # Pydantic schemas
│   ├── services/         # llm_client, vector_store, profile_store
│   ├── retrieval/        # query_router
│   ├── memory/
│   │   ├── working/
│   │   ├── episodic/
│   │   ├── profile/
│   │   └── semantic_rag/ # ingestion → retriever → reranker → generator
│   ├── harness/          # perceive → resolve → retrieve → plan → act → observe → persist
│   ├── mcp_servers/      # mcp_memory, mcp_catalog
│   ├── tools/
│   ├── eval/
│   ├── improvement_loop/
│   └── api/routers/      # chat, calls, health
├── frontend/             # Next.js UI
├── docs/
├── scripts/
├── notebooks/
└── tests/
```

## Bắt đầu nhanh

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # điền API key
```

### Backend

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check: `curl http://localhost:8000/health`

### Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

- Frontend: http://localhost:3000
- Backend:  http://localhost:8000
- Chat API: `POST /api/chat`


## Kiểm thử


```bash
python tests/test_pipeline_rag_real.py
```

Truyền câu hỏi tùy chọn:
```bash
python tests/test_pipeline_rag_real.py "Mình muốn mua điện thoại Samsung dưới 10 triệu còn hàng"
```

Yêu cầu `GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `HF_TOKEN` trong `.env`.

### Kiểm tra Gemini trước khi build

```bash
python tests/test_api_external.py
```

## Docker Compose

```bash
docker compose up --build
```

Dừng:

```bash
docker compose down
docker compose up -d --build
```

Không commit `.env`; chỉ commit `.env.example`.

## Biến môi trường chính

| Biến | Mặc định | Mục đích |
|------|----------|----------|
| `GEMINI_API_KEY` | — | Embedding + sinh câu trả lời |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model chính |
| `GROQ_API_KEY` | — | Fallback LLM |
| `QDRANT_URL` / `QDRANT_API_KEY` | — | Vector store |
| `MONGODB_URI` | — | Document store |
| `HF_TOKEN` | — | Reranker (Hugging Face) |
| `PORT` | `8000` | Port API |
| `UVICORN_RELOAD` | `false` | Auto-reload (dev) |

Sao chép `.env.example` → `.env`. Không commit `.env`.

## Quy ước

- **Không để LLM tự tính số liệu** — giá, tồn kho, KM luôn đi qua `tools/` hoặc `retrieval/`.
- **Mọi fact ghi vào memory phải giữ nguồn** (`source_call_id`, `extracted_at`).
- **`services/` chỉ chứa client wrapper** — business logic nằm ở `harness/` và `retrieval/`.
- Test → `tests/`, thử nghiệm nhanh → `notebooks/`.
```