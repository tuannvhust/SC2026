"""Script ví dụ chạy thử nghiệm hội thoại telesales đa lượt với Agent LangGraph."""

import os
import sys
from pathlib import Path

# Thêm đường dẫn gốc của project vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Tự động nạp biến môi trường từ file .env nếu thư viện python-dotenv đã được cài đặt
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src import build_graph, finalize_call, handle_customer_turn, load_profile


def main():
    print("=" * 60)
    print("Khởi tạo Agent Telesales LangGraph...")
    print("=" * 60)

    graph = build_graph()
    call_id = "call-demo-001"
    customer_phone = "0982000000"
    channel = "voice_call"

    dialogue = [
        "Cho em hỏi máy lọc không khí giá bao nhiêu, phòng 25m2 ngân sách 5tr",
        "Để em hỏi chồng đã rồi báo lại nhé",
    ]

    for turn_idx, user_msg in enumerate(dialogue, 1):
        print(f"\n[Lượt {turn_idx}]")
        print(f"Khách hàng: {user_msg}")
        result = handle_customer_turn(
            graph,
            call_id=call_id,
            customer_phone=customer_phone,
            channel=channel,
            user_message=user_msg,
        )
        print(f"Agent:      {result.get('final_response')}")

    print("\n--- Kết thúc cuộc gọi & Tóm tắt (Finalize Call) ---")
    summary = finalize_call(graph, call_id)
    print(f"Tóm tắt cuộc gọi: {summary}")

    customer_id = result.get("customer_id")
    if customer_id:
        profile = load_profile(customer_id)
        print(f"\nDữ liệu Profile khách hàng lưu trong SQLite: {profile}")

    print("\n" + "=" * 60)
    print("Khách hàng cũ gọi lại trong phiên tiếp theo...")
    print("=" * 60)

    call_id_2 = "call-demo-002"
    user_msg_2 = "Alo, chị hôm trước hỏi máy lọc không khí đây"
    print(f"Khách hàng: {user_msg_2}")
    result_2 = handle_customer_turn(
        graph,
        call_id=call_id_2,
        customer_phone=customer_phone,
        channel=channel,
        user_message=user_msg_2,
    )
    print(f"Agent:      {result_2.get('final_response')}")
    print(f"Cờ nhận diện khách cũ (is_returning_customer): {result_2.get('is_returning_customer')}")


if __name__ == "__main__":
    main()
