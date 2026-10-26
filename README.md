# SC2026

Harness for a Vietnamese sales support agent, with a FastAPI/LangGraph backend
and a Next.js frontend. See [the architecture guide](docs/architecture.md) for
component ownership and [the development guide](docs/development.md) for the
short command reference.

## Cấu trúc thư mục

```text
SC2026/
├── backend/
│   ├── src/                     # FastAPI, agent graph, tools, memory, services
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/                     # Next.js app, feature UI, hooks, types
│   └── Dockerfile
├── data/                        # Reference catalog/policy, schemas, evaluation, ASR
├── generated/
│   └── scenario-dataset/        # Scenarios, transcripts, and generation artifacts
├── scripts/
│   ├── seed/
│   ├── database/
│   └── development/
├── tests/                       # Cross-service and Docker smoke tests
├── docs/                        # Architecture, development, and database notes
├── compose.yaml
├── .dockerignore
├── .gitignore
├── .env.example
├── AGENTS.md
└── pytest.ini
```

Quy ước tên: Python dùng `snake_case` (class dùng `PascalCase`); React component
dùng `PascalCase.tsx`; hook dùng tiền tố `use-`; thư mục và tài liệu mới dùng
`kebab-case`. Dữ liệu benchmark giữ nguyên tên và đường dẫn nguồn để các công
cụ và kịch bản hiện có tiếp tục hoạt động.

## Yêu cầu môi trường

### Chạy local

- Python 3.11 hoặc tương thích.
- Node.js 20.9+ và npm.
- Tài khoản/API key cho các dịch vụ cần dùng.

### Chạy Docker

- Docker Desktop đang chạy Linux containers.
- Docker Compose plugin.

## Cấu hình biến môi trường

Tạo file local từ template:

```powershell
Copy-Item .env.example .env
```

Điền các giá trị thật trong `.env`:

| Biến | Mục đích |
|---|---|
| `GEMINI_API_KEY` | Gemini embedding và sinh câu trả lời |
| `GEMINI_MODEL` | Model sinh câu trả lời chính |
| `GROQ_API_KEY` | Provider fallback |
| `GROQ_MODEL` | Model Groq (mặc định `qwen/qwen3.8-27b`) |
| `USE_GROQ_PRIMARY` | `true` để dùng Groq làm primary |
| `GENERATOR_MAX_TOKENS` | Giới hạn output của generator (optional, mặc định `2048`) |
| `MONGODB_URI` | Kết nối MongoDB Atlas |
| `MONGODB_DB_NAME` | Tên database MongoDB |
| `QDRANT_URL` | URL Qdrant Cloud |
| `QDRANT_API_KEY` | API key Qdrant Cloud |
| `GEMINI_EMBEDDING_MODEL` | Model embedding Gemini |
| `GEMINI_EMBEDDING_DIMENSION` | Kích thước vector, mặc định `768` |
| `GEMINI_EMBEDDING_TIMEOUT` | Timeout embedding giây (optional, mặc định `120`) |
| `SUPABASE_DATABASE_URL` | URL PostgreSQL của Supabase (bắt buộc cho working, episodic và profile facts) |
| `SUPABASE_POOLER_URL` | Supavisor pooler `:6543` cho checkpointer runtime (optional, fallback về DATABASE_URL) |
| `SUPABASE_URL` | Project URL của Supabase, dùng cho catalog, variants, promotions và inventory |
| `SUPABASE_KEY` | Supabase API key có quyền đọc các bảng catalog cần thiết |
| `HF_RERANKER_MODEL` | Model CrossEncoder chạy local/offline, mặc định `BAAI/bge-reranker-base`; model phải có sẵn trong cache Hugging Face |
| `HOST` / `PORT` | Địa chỉ và port backend |



## Graph session memory

StateGraph ghi từng lượt, episode đã hoàn tất và profile facts vào Supabase
PostgreSQL qua SQLAlchemy. Profile facts được ghi đồng thời vào collection
`customer_profile_memories` trên Qdrant Cloud: PostgreSQL là nguồn dữ liệu có
cấu trúc, Qdrant lưu vector và payload của profile facts. Cấu hình
`QDRANT_URL`, `QDRANT_API_KEY`, `GEMINI_API_KEY` và `SUPABASE_DATABASE_URL`
trước khi dùng tính năng memory. Khi kết thúc phiên (`session_ended=true`), graph
mới tổng hợp Episode Memory và chuyển các facts được ghi rõ ràng qua
`memory.write`; hội thoại thường, giá và tồn kho không tự động được lưu thành
Profile Memory. Dữ liệu đã có trong SQLite cũ không được tự động chuyển sang
PostgreSQL.

## Chạy backend local

Trên Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
$env:PYTHONPATH="backend"
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend chạy tại:

- Health: `http://localhost:8000/health`
- Swagger: `http://localhost:8000/docs`
- Chat API: `POST http://localhost:8000/api/chat`

Backend dùng package `src` trong `backend/src`; khi chạy từ repo root cần giữ
`PYTHONPATH=backend` như lệnh phía trên.

Ví dụ request:

```powershell
Invoke-RestMethod `
  -Uri http://localhost:8000/api/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"customer_id":"demo","message":"Mình muốn mua điện thoại Samsung dưới 10 triệu","channel":"chat","metadata":{}}'
```

Để nhận câu trả lời dạng Server-Sent Events (SSE), gửi thêm `"stream":true`.
Mỗi event `data` chứa một chunk trong trường `text`; event cuối có `"done":true`.
Request không bật `stream` vẫn nhận response JSON như trước.

## Chạy frontend local

```powershell
cd frontend
npm install
npm run dev
```

Mở `http://localhost:3000`.

Frontend proxies `/api/chat` through a Next.js route handler to the backend.
When running locally, the default backend URL is `http://127.0.0.1:8000`.
Set `BACKEND_URL` when the backend runs elsewhere:

```powershell
$env:BACKEND_URL="http://127.0.0.1:8000"
npm run dev
```

In Docker Compose, the frontend uses `http://backend:8000`.

Build production:

```powershell
npm run build
npm run start
```

## Chạy bằng Docker Compose

Đảm bảo đã tạo `.env` và Docker Desktop đang chạy:

```powershell
docker compose build
docker compose up -d
docker compose ps
```

Các service:

| Service | URL |
|---|---|
| Backend | `http://localhost:8000` |
| Frontend | `http://localhost:3000` |

Xem log:

```powershell
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
```

Dừng stack:

```powershell
docker compose down
```

Kiểm tra cấu hình Compose mà không resolve giá trị biến môi trường:

```powershell
docker compose config --no-interpolate
```

Không dùng `docker compose config` bình thường khi output có thể được chia sẻ,
vì Compose có thể render secret từ `.env`.

## Kiểm thử

Chạy toàn bộ Python tests:

```powershell
python -m pytest -q
```

Chạy frontend build:

```powershell
npm --prefix frontend run build
```

Sau khi Compose đang chạy, chạy smoke test:

```powershell
python tests/test_docker_stack.py
```

Smoke test kiểm tra:

1. Backend `/health`.
2. Frontend page.
3. Frontend proxy tới `/api/chat`.

Các test gọi API thật có thể cần credential và dịch vụ bên ngoài:

```powershell
python backend/tests/integration/test_api_external.py
python backend/tests/integration/test_pipeline_rag_real.py
```

Không chạy các test integration này trong CI nếu chưa cấu hình secret tương ứng.

## Dữ liệu và file local

`data/` giữ dữ liệu tham chiếu, chính sách, schema, ASR và evaluation ở các
đường dẫn được code sử dụng. `generated/scenario-dataset/` giữ các scenario,
transcript và artifacts đã sinh. Không đưa secret, cơ sở dữ liệu local, cache
Qdrant/BM25 hoặc output chạy thử vào Git. Xem `.gitignore` để biết các mẫu bị bỏ
qua.
