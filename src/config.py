"""Shared application clients and their lifecycle."""

import os
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from src.services.gemini_embedder import GeminiDenseEmbedder
from src.services.mongo_store import MongoStore
from src.services.vector_store import QdrantVectorStore

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
    google_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
    temperature=0.3,
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
