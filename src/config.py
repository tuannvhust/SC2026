"""Shared application clients and their lifecycle."""

import os
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from src.services.gemini_embedder import GeminiDenseEmbedder
from src.services.mongo_store import MongoStore
from src.services.vector_store import QdrantVectorStore

load_dotenv()


def _build_chat_llm(model_name: str, api_key: Optional[str]):
    if not api_key:
        return None
    model_options: Dict[str, Any] = {
        "model": model_name,
        "google_api_key": api_key,
        "max_retries": 1,
    }
    if model_name != "gemini-3.6-flash":
        model_options["temperature"] = 0.3
    return ChatGoogleGenerativeAI(**model_options)


def _build_groq_llm(model_name: str, api_key: Optional[str]):
    if not api_key:
        return None
    return ChatGroq(model=model_name, groq_api_key=api_key, temperature=0.3, max_retries=2)


def with_groq_fallback(primary, fallback):
    """Attach the configured Groq model as a fallback or use Groq directly if configured as primary."""
    use_groq_primary = os.getenv("USE_GROQ_PRIMARY", "false").lower() in ("true", "1", "yes")
    if use_groq_primary and fallback is not None:
        return fallback.with_fallbacks([primary]) if primary is not None else fallback
    if primary is None:
        return fallback
    if fallback is None:
        return primary
    return primary.with_fallbacks([fallback])


_primary_model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
_gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

llm = _build_chat_llm(_primary_model_name, _gemini_api_key)
groq_llm = _build_groq_llm(
    os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    os.getenv("GROQ_API_KEY"),
)


@dataclass
class SharedConnections:
    mongo_store: MongoStore
    vector_store: QdrantVectorStore
    dense_embedder: GeminiDenseEmbedder


_connections: Optional[SharedConnections] = None
_connections_lock = Lock()


def get_shared_connections() -> SharedConnections:
    """Return process-wide service clients, constructing them only once."""
    global _connections
    if _connections is None:
        with _connections_lock:
            if _connections is None:
                _connections = SharedConnections(
                    mongo_store=MongoStore(),
                    vector_store=QdrantVectorStore(),
                    dense_embedder=GeminiDenseEmbedder(),
                )
    return _connections


def close_shared_connections() -> None:
    """Close initialized client resources when the application stops."""
    global _connections
    with _connections_lock:
        connections = _connections
        _connections = None

    if connections is None:
        return

    connections.mongo_store.close()
    connections.vector_store.close()
    connections.dense_embedder.session.close()
