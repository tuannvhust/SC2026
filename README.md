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
| `GENERATOR_MAX_TOKENS` | Giới hạn output của generator |
| `MONGODB_URI` | Kết nối MongoDB Atlas |
| `MONGODB_DB_NAME` | Tên database MongoDB |
| `QDRANT_URL` | URL Qdrant Cloud |
| `QDRANT_API_KEY` | API key Qdrant Cloud |
| `GEMINI_EMBEDDING_MODEL` | Model embedding Gemini |
| `GEMINI_EMBEDDING_DIMENSION` | Kích thước vector, mặc định `768` |
| `HF_TOKEN` | Token Hugging Face reranker |
| `HF_RERANKER_API_URL` | Endpoint reranker |
| `HF_RERANKER_TIMEOUT` | Timeout request reranker |
| `HOST` / `PORT` | Địa chỉ và port backend |

Không commit `.env`, không ghi API key vào source code và không in toàn bộ
environment trong log. Chỉ commit `.env.example`.

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

## Chạy frontend local

```powershell
cd frontend
npm install
npm run dev
```

Mở `http://localhost:3000`.

Frontend có thể dùng biến:

```powershell
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"
npm run dev
```

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