import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import close_shared_connections, get_shared_connections
from src.api.routers import health, chat, calls
from src.memory.semantic_rag.orchestrator import clear_components

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.shared_connections = get_shared_connections()
    try:
        yield
    finally:
        clear_components()
        app.state.shared_connections = None
        close_shared_connections()


app = FastAPI(
    title="SC2026 - Telesale Harness Agent API",
    description="Harness Agent hỗ trợ telesale e-commerce đa phiên, đa kênh",
    version="1.0.0",
    lifespan=lifespan,
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
    uvicorn.run(
        "src.api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("UVICORN_RELOAD", "false").lower() == "true",
    )
