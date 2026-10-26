"""Stable provenance helpers for generated artifacts."""

from __future__ import annotations

import hashlib
import json


def brief_digest(brief: dict) -> str:
    """Hash generation inputs, excluding post-generation/legacy goal metadata."""
    canonical = {key: value for key, value in brief.items() if key != "_matrix_hints"}
    if isinstance(canonical.get("calls"), list):
        canonical["calls"] = [
            {key: value for key, value in call.items() if key != "customer_goal"}
            for call in canonical["calls"]
        ]
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
