"""Smoke-test the Docker Compose frontend/backend connection."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
TIMEOUT_SECONDS = 120


def request(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, bytes]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    try:
        with urlopen(
            Request(url, data=body, headers=headers, method=method),
            timeout=TIMEOUT_SECONDS,
        ) as response:
            return response.status, response.read()
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} returned HTTP {error.code}: {details}") from error
    except URLError as error:
        raise RuntimeError(f"{method} {url} could not connect: {error.reason}") from error


def main() -> int:
    checks = [
        ("backend health", f"{BACKEND_URL}/health", "GET", None),
        ("frontend page", FRONTEND_URL, "GET", None),
        (
            "frontend-to-backend chat proxy",
            f"{FRONTEND_URL}/api/chat",
            "POST",
            {
                "customer_id": "docker-smoke-test",
                "message": "Mình muốn mua điện thoại Samsung",
                "channel": "chat",
                "metadata": {},
            },
        ),
    ]

    for name, url, method, payload in checks:
        try:
            status, body = request(url, method, payload)
            if status < 200 or status >= 300:
                raise RuntimeError(f"unexpected HTTP status {status}")
            if name == "frontend-to-backend chat proxy":
                response = json.loads(body)
                if not isinstance(response.get("reply"), str):
                    raise RuntimeError("response does not contain a string 'reply'")
            print(f"[PASS] {name}: HTTP {status}")
        except (RuntimeError, json.JSONDecodeError) as error:
            print(f"[FAIL] {name}: {error}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
