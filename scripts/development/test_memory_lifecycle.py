"""Independent P2 memory lifecycle check (no LLM calls)."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.graph.nodes import persistence_nodes
from src.graph.nodes.input_nodes import build_call_brief_node
from src.memory.working.postgres_store import PostgresMemoryStore


class _NoVectorConnections:
    class _VS:
        def init_collection(self, *args, **kwargs):
            raise RuntimeError("vector disabled in lifecycle script")

    vector_store = _VS()
    dense_embedder = None


def _mask(value: str) -> str:
    return f"{value[:4]}***{value[-3:]}" if len(value) > 8 else "***"


def main() -> int:
    print("=== P2 memory lifecycle (no LLM) ===")
    database_url = (
        os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DATABASE_URL") or ""
    ).strip()
    using_real_db = bool(database_url)
    if using_real_db:
        print("database: configured real DB")
        store = PostgresMemoryStore(database_url)
    else:
        tmp = Path(tempfile.gettempdir()) / f"p2-{uuid.uuid4().hex[:8]}.sqlite3"
        print(f"database: local sqlite {tmp.name} (set DATABASE_URL for real DB)")
        store = PostgresMemoryStore(f"sqlite+pysqlite:///{tmp}")

    persistence_nodes._store = store
    results = {}
    customer_id = f"CUST-P2-{uuid.uuid4().hex[:6].upper()}"
    session_a = f"SESSION-P2-A-{uuid.uuid4().hex[:6]}"
    session_b = f"SESSION-P2-B-{uuid.uuid4().hex[:6]}"
    print(f"customer={_mask(customer_id)} a={session_a[-8:]} b={session_b[-8:]}")

    try:
        persistence_nodes.persist_turn_node(
            {
                "messages": [HumanMessage(content="Toi ten Lan")],
                "session_id": session_a,
                "turn_id": "turn-1",
                "customer_id": customer_id,
                "customer_info": {"phone": "0912345678", "name": "Lan"},
                "input_valid": True,
            }
        )
        events = store.get_session_events(session_a)
        ok = len(events) == 1 and events[0]["customer_id"] == customer_id
        print(f"[1] working events={len(events)} ok={ok}")
        results["working"] = "PASS" if ok else "FAIL"
    except Exception as error:
        print(f"[1] working BLOCKED: {type(error).__name__}: {error}")
        results["working"] = "BLOCKED"

    try:
        from src.memory.profile.profile_store import ProfileStore

        profile = ProfileStore(postgres_store=store, connections=_NoVectorConnections())
        profile.add_profile_facts(
            customer_id=customer_id, facts=[{"key": "size", "value": "M"}],
            session_id=session_a,
        )
        profile.add_profile_facts(
            customer_id=customer_id, facts=[{"key": "size", "value": "L"}],
            session_id=session_a,
        )
        facts = profile.get_profile_facts(customer_id)
        history = store.get_profile_fact_history(customer_id, "size")
        ok = facts.get("size") == "L" and len(history) == 2
        print(f"[2] profile size={facts.get('size')} history={len(history)} ok={ok}")
        results["profile"] = "PASS" if ok else "FAIL"
    except Exception as error:
        print(f"[2] profile BLOCKED: {type(error).__name__}: {error}")
        results["profile"] = "BLOCKED"

    try:
        messages = [
            HumanMessage(content="Ngan sach 5 trieu"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "memory.write",
                        "args": {
                            "key": "budget", "value": "5 trieu",
                            "provenance_session_id": session_a,
                        },
                        "id": "mem-1", "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(name="memory.write", content="{'status': 'ok'}", tool_call_id="mem-1"),
        ]
        persistence_nodes.persist_turn_node(
            {
                "messages": messages, "session_id": session_a, "turn_id": "turn-2",
                "customer_id": customer_id, "customer_info": {"phone": "0912345678"},
                "input_valid": True, "session_ended": True,
            }
        )
        from src.memory.profile.profile_store import ProfileStore as _PS

        persistence_nodes.get_profile_store = lambda: _PS(  # type: ignore
            postgres_store=store, connections=_NoVectorConnections()
        )
        end_state = {
            "messages": messages, "session_id": session_a, "customer_id": customer_id,
            "customer_info": {"phone": "0912345678", "channel": "web_chat"},
            "session_ended": True,
        }
        first = persistence_nodes.persist_call_node(end_state)
        second = persistence_nodes.persist_call_node(end_state)
        episode = store.get_episode(session_a)
        ok = episode is not None and second.get("already_finalized") is True
        print(f"[3] episode={'yes' if episode else 'no'} idempotent={second.get('already_finalized')} ok={ok}")
        results["episodic"] = "PASS" if ok else "FAIL"
    except Exception as error:
        print(f"[3] episodic BLOCKED: {type(error).__name__}: {error}")
        results["episodic"] = "BLOCKED"

    try:
        brief = build_call_brief_node(
            {
                "messages": [HumanMessage(content="Tu van tiep")],
                "session_id": session_b, "customer_id": customer_id,
                "customer_info": {"phone": "0912345678", "channel": "web_chat"},
            }
        )["call_brief"]
        last = brief.get("last_session") or {}
        ok = "size" in (brief.get("profile_facts") or {}) and last.get("session_id") == session_a
        print(f"[4] continuity profile_size={'size' in (brief.get('profile_facts') or {})} last={str(last.get('session_id'))[-8:]} ok={ok}")
        results["continuity"] = "PASS" if ok else "FAIL"
        results["callbrief"] = "PASS" if ok else "FAIL"
    except Exception as error:
        print(f"[4] continuity BLOCKED: {type(error).__name__}: {error}")
        results["continuity"] = "BLOCKED"
        results["callbrief"] = "BLOCKED"

    print("--- summary ---")
    for key in ("working", "profile", "episodic", "continuity", "callbrief"):
        print(f"{key}: {results.get(key)}")
    return 1 if any(v != "PASS" for v in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())

