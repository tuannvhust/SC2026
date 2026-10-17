"""scripts/demo_graph.py
Interactive CLI testing script for LangGraph execution stream.
"""

import sys
import asyncio

# Khai báo Event Loop Policy cho Windows ngay từ dòng đầu tiên
# Thêm `# type: ignore` để Pylance không báo warning
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore

import argparse
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import logging

# Show planner prompt size / estimated tokens (Bước 6: đo context Groq).
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("src.graph.nodes.planner").setLevel(logging.DEBUG)
logging.getLogger("src.graph.nodes.input_nodes").setLevel(logging.DEBUG)

from langchain_core.messages import HumanMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def main():
    parser = argparse.ArgumentParser(description="Interactive LangGraph demo tester.")
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Run without Postgres checkpointer (MemorySaver) for offline dev.",
    )
    args = parser.parse_args()

    # Lazy import builder bên trong hàm async để tránh khởi tạo Connection Pool ở top-level
    from src.graph.builder import (
        _is_pool_connection_error,
        close_graph_async_checkpointer,
        graph,
        initialize_graph_async_checkpointer,
        reopen_graph_async_checkpointer,
    )

    checkpoint_ready = False
    if args.no_checkpoint:
        from langgraph.checkpoint.memory import MemorySaver

        graph.install_checkpointer(MemorySaver())
        print("[INFO] Running with in-memory checkpointer (--no-checkpoint).")
    else:
        try:
            await initialize_graph_async_checkpointer()
            checkpoint_ready = True
        except Exception as error:
            print(f"[WARN] Không kết nối được Postgres checkpointer: {error}")
            print("[INFO] Fallback sang --no-checkpoint (MemorySaver) để test tiếp.")
            from langgraph.checkpoint.memory import MemorySaver

            graph.install_checkpointer(MemorySaver())

    try:
        session_id = f"test-{uuid.uuid4().hex[:6]}"
        config = {"configurable": {"thread_id": session_id}}

        print(f"\n[DEV TESTER] Session: {session_id}")
        print("[INFO] Nhập 'end' hoặc 'exit' để thoát.\n" + "-" * 50)

        turn = 1
        while True:
            try:
                query = await asyncio.to_thread(input, f"\n[Turn {turn}] User > ")
            except (KeyboardInterrupt, EOFError):
                print("\n[INFO] Thoát session test.")
                break

            query = query.strip()
            if query.lower() in {"end", "exit"}:
                print("\n[INFO] Kết thúc phiên test + finalize memory...")
                try:
                    from src.api.routers.graph_runner import finalize_session

                    finalized = await asyncio.to_thread(
                        finalize_session, session_id=session_id
                    )
                    print(
                        f"[INFO] Finalized: working_events={finalized['working_events']} "
                        f"episode={'yes' if finalized['episode'] else 'no'} "
                        f"already={finalized['already_finalized']} "
                        f"empty={finalized['empty_session']}"
                    )
                except Exception as error:
                    print(f"[WARN] Finalize thất bại: {type(error).__name__}: {error}")
                break
            if not query:
                continue

            state_input = {
                "messages": [HumanMessage(content=query)],
                "session_id": session_id,
                "turn_id": f"turn-{turn}",
                "turn_number": turn,
            }
            # Restore verified identity across turns (stateless runs / retries).
            from src.api.routers.graph_runner import _restore_identity_from_events
            from src.memory.working.postgres_store import get_postgres_memory_store
            from langchain_core.messages import messages_from_dict

            past_events = get_postgres_memory_store().get_session_events(session_id)
            restored = _restore_identity_from_events(past_events)
            if restored.get("customer_id"):
                state_input["customer_id"] = restored["customer_id"]
            info_patch = restored.get("customer_info_patch") or {}
            if info_patch:
                state_input["customer_info"] = dict(info_patch)
            if restored.get("identity_attempts"):
                state_input["identity_attempts"] = restored["identity_attempts"]
            if restored.get("pending_need"):
                state_input["pending_need"] = restored["pending_need"]
            if not getattr(graph, "checkpointer_enabled", False):
                history_msgs = []
                for past in past_events:
                    serialized = past.get("payload", {}).get("messages", [])
                    if serialized:
                        history_msgs.extend(messages_from_dict(serialized))
                if history_msgs:
                    state_input["messages"] = [*history_msgs, *state_input["messages"]]

            print(f"\n>>> Đang chạy graph cho turn {turn}...")
            step = 1

            try:
                stream = graph.astream(state_input, config)
            except Exception as error:
                if checkpoint_ready and _is_pool_connection_error(error):
                    print(f"[WARN] Pool checkpointer rớt: {error}")
                    print("[INFO] Reopen pool 1 lần rồi chạy lại turn này...")
                    await reopen_graph_async_checkpointer()
                    stream = graph.astream(state_input, config)
                else:
                    raise

            try:
                async for event in stream:
                    for node, update in event.items():
                        print(f"  [{step}] Node: [{node}]")
                        step += 1

                        if not isinstance(update, dict):
                            continue

                        if "input_valid" in update:
                            print(f"       -> Input Valid: {update['input_valid']}")
                        if "output_valid" in update:
                            print(f"       -> Output Valid: {update['output_valid']}")
                            if update.get("guardrail_feedback"):
                                print(f"       [!] Guardrail Feedback / Lý do lỗi:\n           {update['guardrail_feedback']}")
                        if "customer_id" in update:
                            print(f"       -> Resolved Customer ID: {update['customer_id']}")

                        if "messages" in update and update["messages"]:
                            msg = update["messages"][-1]
                            m_type = getattr(msg, "type", "unknown")

                            if tool_calls := getattr(msg, "tool_calls", None):
                                for tc in tool_calls:
                                    print(f"       -> Tool Call: {tc.get('name')} | Args: {tc.get('args')}")
                            elif m_type == "tool":
                                print(f"       -> Tool Output ({getattr(msg, 'name', 'N/A')}): {msg.content}")
                            elif msg.content:
                                content_str = msg.content
                                if isinstance(content_str, list):
                                    content_str = " ".join(
                                        str(item["text"])
                                        for item in content_str
                                        if isinstance(item, dict) and "text" in item
                                    )
                                print(f"       -> Agent Response ({m_type}): {content_str}")
            except Exception as error:
                if checkpoint_ready and _is_pool_connection_error(error):
                    print(f"[WARN] Turn {turn} rớt pool giữa chừng: {error}")
                    print("[INFO] Reopen pool 1 lần — turn này giữ lại, bạn Enter để chạy lại.")
                    await reopen_graph_async_checkpointer()
                    continue
                raise

            print("-" * 50)
            turn += 1
    finally:
        await close_graph_async_checkpointer()


if __name__ == "__main__":
    asyncio.run(main())