"""scripts/demo_graph.py
Interactive CLI testing script for LangGraph execution stream.
"""

import sys
import asyncio

# Khai báo Event Loop Policy cho Windows ngay từ dòng đầu tiên
# Thêm `# type: ignore` để Pylance không báo warning
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore

import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def main():
    # Lazy import builder bên trong hàm async để tránh khởi tạo Connection Pool ở top-level
    from src.graph.builder import (
        close_graph_async_checkpointer,
        graph,
        initialize_graph_async_checkpointer,
    )

    await initialize_graph_async_checkpointer()

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
                print("\n[INFO] Kết thúc phiên test.")
                break
            if not query:
                continue

            state_input = {
                "messages": [HumanMessage(content=query)],
                "session_id": session_id,
                "turn_id": f"turn-{turn}",
                "turn_number": turn,
            }

            print(f"\n>>> Đang chạy graph cho turn {turn}...")
            step = 1

            async for event in graph.astream(state_input, config):
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

            print("-" * 50)
            turn += 1
    finally:
        await close_graph_async_checkpointer()


if __name__ == "__main__":
    asyncio.run(main())