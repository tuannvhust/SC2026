# SC2026

## Cấu trúc thư mục

```text
SC2026/
├── data/
│   └── catalog/                 # Dữ liệu catalog nguồn
├── frontend/                    # Next.js + React + Tailwind UI
├── scripts/                     # Seed/sync dữ liệu
├── src/
│   ├── api/                     # FastAPI app và API routers
│   ├── config.py                # Kết nối dịch vụ dùng chung, theo vòng đời ứng dụng
│   ├── memory/semantic_rag/     # Router, rewrite, retrieval, rerank, generate
│   └── services/                # Gemini, MongoDB, Qdrant, BM25 clients
├── tests/                       # Unit, integration và smoke tests
├── compose.yaml
├── Dockerfile.backend
├── Dockerfile.frontend
├── requirements.txt
├── .env.example
└── .env
```

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
| `GROQ_MODEL` | Model Groq |
| `GENERATOR_MAX_TOKENS` | Giới hạn output của generator (mặc định `2048`) |
| `MONGODB_URI` | Kết nối MongoDB Atlas |
| `MONGODB_DB_NAME` | Tên database MongoDB |
| `QDRANT_URL` | URL Qdrant Cloud |
| `QDRANT_API_KEY` | API key Qdrant Cloud |
| `GEMINI_EMBEDDING_MODEL` | Model embedding Gemini |
| `GEMINI_EMBEDDING_DIMENSION` | Kích thước vector, mặc định `768` |
| `SUPABASE_DATABASE_URL` | URL PostgreSQL của Supabase (bắt buộc cho working, episodic và profile facts) |
| `HF_RERANKER_MODEL` | Model CrossEncoder chạy local/offline, mặc định `BAAI/bge-reranker-base`; model phải có sẵn trong cache Hugging Face |
| `HOST` / `PORT` | Địa chỉ và port backend |

Không commit `.env`, không ghi API key vào source code và không in toàn bộ
environment trong log. Chỉ commit `.env.example`.

Backend dùng chung client MongoDB, Qdrant và Gemini embedding trong một process.
Các client được tạo khi ứng dụng khởi động và được đóng khi ứng dụng dừng.
Product payloads trong Qdrant chỉ chứa metadata tĩnh; giá và tồn kho phải được
lấy từ dịch vụ catalog/pricing/inventory hiện hành, không dùng làm bộ lọc Qdrant.
Chạy lại bước đồng bộ catalog để ghi đè payload cũ đã chứa trường biến động.
Reranker chạy local bằng Sentence Transformers, không gọi Hugging Face Inference
API và không cần `HF_TOKEN`. Chế độ offline yêu cầu model đã được tải và có sẵn
trong cache Hugging Face trên máy. FastAPI nạp model và chạy warmup trong
`lifespan` trước khi nhận request; server sẽ báo lỗi khởi động nếu model không
có sẵn trong cache.

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
pip install -r requirements.txt
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend chạy tại:

- Health: `http://localhost:8000/health`
- Swagger: `http://localhost:8000/docs`
- Chat API: `POST http://localhost:8000/api/chat`

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
python -m pytest tests -q
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
python tests/test_api_external.py
python tests/test_pipeline_rag_real.py
```

Không chạy các test integration này trong CI nếu chưa cấu hình secret tương ứng.