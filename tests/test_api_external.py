"""Diagnose Gemini API access without printing API keys."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv


BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-embedding-001"
DEFAULT_DIMENSION = 768


def normalize_model_name(model: str) -> str:
    return model.strip().removeprefix("models/")


def error_summary(response: requests.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        return response.text[:300]

    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    return str(
        {
            "status": error.get("status"),
            "message": error.get("message"),
        }
    )


def main() -> int:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = normalize_model_name(
        os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_MODEL)
    )
    dimension = int(os.getenv("GEMINI_EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION)))

    print(f"GEMINI_API_KEY: {'configured' if api_key else 'missing'}")
    if not api_key:
        print("Set GEMINI_API_KEY in .env.")
        return 1

    print(f"Embedding model: {model}")
    print(f"Requested embedding dimensions: {dimension}")

    try:
        models_response = requests.get(
            f"{BASE_URL}/models",
            params={"key": api_key},
            timeout=20,
        )
    except requests.RequestException as exc:
        print(f"Model listing failed ({type(exc).__name__}).")
        return 1

    print(f"GET /models: HTTP {models_response.status_code}")
    if not models_response.ok:
        print(error_summary(models_response))
        return 1

    available_models = models_response.json().get("models", [])
    embedding_models = [
        normalize_model_name(item.get("name", ""))
        for item in available_models
        if "embedContent" in item.get("supportedGenerationMethods", [])
    ]
    print(f"Embedding models visible to this key: {embedding_models}")
    if model not in embedding_models:
        print(
            f"Configured model '{model}' is not available for embedContent "
            "with this API key."
        )
        if "gemini-embedding-001" in embedding_models:
            print(
                "Set GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001 "
                "in .env and retry."
            )
        return 1

    payload = {
        "model": f"models/{model}",
        "content": {"parts": [{"text": "Kiểm tra quyền embedding Gemini"}]},
        "outputDimensionality": dimension,
    }
    try:
        embedding_response = requests.post(
            f"{BASE_URL}/models/{model}:embedContent",
            params={"key": api_key},
            json=payload,
            timeout=20,
        )
    except requests.RequestException as exc:
        print(f"Embedding request failed ({type(exc).__name__}).")
        return 1

    print(f"POST /models/{model}:embedContent: HTTP {embedding_response.status_code}")
    if not embedding_response.ok:
        print(error_summary(embedding_response))
        return 1

    values = embedding_response.json().get("embedding", {}).get("values", [])
    print(f"Embedding request succeeded; dimensions: {len(values)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
