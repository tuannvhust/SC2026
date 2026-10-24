"""Regression test for Postgres pool recovery (Turn 2 pool-1 errors)."""

from src.graph import builder
from src.memory.working import postgres_store


def test_checkpointer_prefers_pooler_url(monkeypatch):
    monkeypatch.setenv(
        "SUPABASE_DATABASE_URL", "postgresql://postgres:pw@db.ref.supabase.co:5432/postgres"
    )
    monkeypatch.setenv(
        "SUPABASE_POOLER_URL",
        "postgresql://postgres.ref:pw@aws-0-pooler.supabase.com:6543/postgres",
    )
    assert postgres_store.checkpointer_database_url().endswith(":6543/postgres")
    assert "postgres.ref" in postgres_store.checkpointer_database_url()

    monkeypatch.delenv("SUPABASE_POOLER_URL", raising=False)
    assert postgres_store.checkpointer_database_url().endswith(":5432/postgres")


def test_checkpointer_falls_back_without_pooler(monkeypatch):
    """New .env.example omits SUPABASE_POOLER_URL: direct URL must still work."""
    monkeypatch.delenv("SUPABASE_POOLER_URL", raising=False)
    monkeypatch.setenv(
        "SUPABASE_DATABASE_URL", "postgresql://postgres:pw@db.ref.supabase.co:5432/postgres"
    )
    assert postgres_store.checkpointer_database_url().endswith(":5432/postgres")


def test_groq_default_model_matches_env_example(monkeypatch):
    """GROQ_MODEL default must match .env.example (qwen/qwen3.8-27b)."""
    import importlib

    import src.config as config_module
    import src.memory.semantic_rag.generator as generator_module

    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    reloaded = importlib.reload(config_module)
    assert reloaded.groq_llm is not None
    assert reloaded.groq_llm.model_name == "qwen/qwen3.8-27b"
    assert generator_module.RAGGenerator(llm_client=object()).groq_model == "qwen/qwen3.8-27b"


def test_pool_connection_error_detection():
    assert builder._is_pool_connection_error(
        RuntimeError("error connecting in 'pool-1': connection failed")
    )
    assert builder._is_pool_connection_error(
        RuntimeError("server closed the connection unexpectedly")
    )
    assert not builder._is_pool_connection_error(ValueError("bad input"))


def test_describe_database_url_masks_credentials():
    described = postgres_store.describe_database_url(
        "postgresql://postgres:secret@db.ref.supabase.co:5432/postgres?sslmode=require"
    )
    assert "secret" not in described
    assert "db.ref.supabase.co:5432/postgres" in described
