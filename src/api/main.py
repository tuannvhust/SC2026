import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import close_shared_connections, get_shared_connections
from src.api.routers import health, chat, calls, reference_data
from src.graph.builder import close_graph_checkpointer, initialize_graph_checkpointer
from src.memory.semantic_rag.orchestrator import clear_components, warmup_reranker
from src.graph.nodes.persistence_nodes import close_working_memory_store

load_dotenv()

logger = logging.getLogger(__name__)
trace_logger = logging.getLogger("src.graph.trace")


def _model_name(client: Any) -> str:
    if client is None:
        return "none"
    return str(
        getattr(client, "model", None)
        or getattr(client, "model_name", None)
        or "unknown"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.shared_connections = get_shared_connections()
    try:
        initialize_graph_checkpointer()
        warmup_reranker()
        from src.config import groq_llm, llm

        trace_logger.info(
            "[SERVER] startup trace_level=%s llm_primary=%s llm_fallback=%s",
            os.getenv("GRAPH_TRACE_LEVEL", "info"),
            _model_name(llm),
            _model_name(groq_llm),
        )
        yield
    finally:
        clear_components()
        close_graph_checkpointer()
        close_working_memory_store()
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
app.include_router(reference_data.router, prefix="/api", tags=["Reference data"])

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("UVICORN_RELOAD", "false").lower() == "true",
    )
