import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import health, chat, calls

app = FastAPI(
    title="SC2026 - Telesale Harness Agent API",
    description="Harness Agent hỗ trợ telesale e-commerce đa phiên, đa kênh",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(calls.router, prefix="/api", tags=["Calls"])

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)

