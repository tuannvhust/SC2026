"""
cli_chat.py
Giao diện dòng lệnh (CLI) tương tác trực tiếp với Agent Telesales (LangGraph + Semantic RAG).
Tự động ghi nhận log trace vào file JSONL sau mỗi lượt thoại.

Cách chạy:
    $env:PYTHONUTF8=1; python cli_chat.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Cấu hình UTF-8 cho console Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stdin and hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

# Nạp biến môi trường từ .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Đảm bảo đường dẫn import
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph_agent.src.graph import build_graph, handle_customer_turn, finalize_call
from langgraph_agent.src.memory import load_profile


def print_banner():
    print("=" * 70)
    print("  AI AGENT TELESALES - INTERACTIVE CHAT (LangGraph + Semantic RAG) ")
    print("=" * 70)
    print("  Lệnh hỗ trợ:")
    print("    • /end   : Kết thúc cuộc gọi và xuất bản tóm tắt cuộc gọi")
    print("    • /new   : Bắt đầu một cuộc gọi mới (khách hàng quay lại)")
    print("    • /trace : Xem chi tiết trace của lượt thoại vừa xong")
    print("    • exit   : Thoát chương trình")
    print("=" * 70)


def main():
    print_banner()

    # Tạo thư mục runs để chứa trace log nếu chưa có
    runs_dir = ROOT / "runs"
    runs_dir.mkdir(exist_ok=True)

    default_phone = "0987654321"
    phone_input = input(f"\nNhập số điện thoại khách hàng (Enter để dùng '{default_phone}'): ").strip()
    customer_phone = phone_input if phone_input else default_phone

    # Khởi tạo Graph
    print("\n⏳ Đang khởi tạo LangGraph và kiểm tra các Tool/RAG...")
    graph = build_graph()
    print(" Agent đã sẵn sàng!\n")

    call_index = 1
    call_id = f"call-{uuid.uuid4().hex[:6]}"
    trace_file = runs_dir / f"trace_{customer_phone}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    print(f"Cuộc gọi #{call_index} đã bắt đầu (ID: {call_id})")
    print(f"File log trace: {trace_file.relative_to(ROOT)}")
    print("-" * 70)

    turn = 1
    last_result = None

    while True:
        try:
            user_msg = input("\n[Khách hàng] > ").strip()
            if not user_msg:
                continue

            if user_msg.lower() in ("exit", "quit", "q"):
                print("\n Tạm biệt! Đã kết thúc phiên làm việc.")
                break

            if user_msg == "/end":
                print("\n📞 --- Đang kết thúc cuộc gọi & tạo tóm tắt ---")
                summary = finalize_call(graph, call_id)
                print(f"📋 Tóm tắt cuộc gọi: {summary}")
                
                # Hiển thị profile vừa lưu
                cid = (last_result or {}).get("customer_id")
                if cid:
                    prof = load_profile(cid)
                    print(f"💾 Hồ sơ khách hàng (Profile) lưu trong SQLite: {prof}")
                print("-" * 70)
                continue

            if user_msg == "/new":
                call_index += 1
                call_id = f"call-{uuid.uuid4().hex[:6]}"
                turn = 1
                print(f"\n📞 Bắt đầu cuộc gọi tiếp theo #{call_index} (ID: {call_id})")
                print("Hệ thống sẽ tự động nhận diện nếu đây là khách hàng cũ.")
                print("-" * 70)
                continue

            if user_msg == "/trace":
                if not last_result:
                    print(" Chưa có lượt thoại nào để xem trace.")
                    continue
                print("\n🔍 --- CHI TIẾT TRACE LƯỢT GẦN NHẤT ---")
                print(f"• Tool Calls / RAG: {json.dumps(last_result.get('tool_results', []), ensure_ascii=False, indent=2)}")
                print(f"• Guardrail Passed: {last_result.get('guardrail_passed')}")
                print(f"• Facts ghi nhớ:    {last_result.get('facts_to_persist')}")
                print(f"• Trạng thái:       {last_result.get('call_outcome') or 'đang tiếp diễn'}")
                print("-" * 70)
                continue

            # Gọi LangGraph xử lý lượt thoại
            res = handle_customer_turn(
                graph,
                call_id=call_id,
                customer_phone=customer_phone,
                channel="voice_call",
                user_message=user_msg,
                turn=turn,
                trace_path=str(trace_file),
            )
            last_result = res

            # Kiểm tra xem có tool hoặc RAG nào được gọi không để hiển thị badge
            tools_used = [t.get("tool") or t.get("name") for t in res.get("tool_results", [])]
            badge = f" [🔧 Đã gọi: {', '.join(tools_used)}]" if tools_used else ""

            agent_reply = res.get("final_response") or res.get("draft_response") or "(Không có phản hồi)"
            print(f"[Agent]       > {agent_reply}{badge}")

            turn += 1

        except KeyboardInterrupt:
            print("\n\nĐã nhận lệnh ngắt từ bàn phím. Thoát chương trình.")
            break
        except Exception as e:
            print(f"\n⚠️ Lỗi trong quá trình xử lý lượt thoại: {e}")


if __name__ == "__main__":
    main()

