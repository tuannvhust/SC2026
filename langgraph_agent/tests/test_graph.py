import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

# Đảm bảo đường dẫn gốc langgraph_agent nằm trong sys.path
AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src import (
    TOOLS,
    build_graph,
    extract_money,
    finalize_call,
    handle_customer_turn,
    load_profile,
)
from src import llm, nodes


@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    """Thiết lập môi trường cô lập cho mỗi test với SQLite DB tạm thời và LLM stand-in offline."""
    test_db = str(tmp_path / "test.db")
    monkeypatch.setenv("HARNESS_DB", test_db)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    graph = build_graph()
    phone = "0982000111"
    return {"graph": graph, "phone": phone, "db_path": test_db}


def test_call_1_new_customer(test_setup):
    """Cuộc gọi 1: Khách hàng mới hỏi giá và nêu lý do cản trở (cần hỏi chồng)."""
    g = test_setup["graph"]
    phone = test_setup["phone"]

    r = handle_customer_turn(
        g, "c1", phone, "voice_call", "Cho em hỏi máy lọc không khí giá bao nhiêu, phòng 25m2 ngân sách 5tr"
    )
    assert "4.890.000" in r["final_response"]
    assert r["is_returning_customer"] is False

    r2 = handle_customer_turn(g, "c1", phone, "voice_call", "Để em hỏi chồng đã")
    summary = finalize_call(g, "c1")
    assert summary is not None

    profile = load_profile(r["customer_id"])
    assert profile["room_area_m2"] == 25
    assert profile["product_advised"] == "SKU-AP-X"
    assert profile["blocker"] == "cần hỏi người nhà"


def test_call_2_returning_customer_and_order(test_setup):
    """Cuộc gọi 2: Khách hàng cũ gọi lại, tiếp nối ngữ cảnh và chốt đơn thành công."""
    g = test_setup["graph"]
    phone = test_setup["phone"]

    # Khởi tạo dữ liệu từ Cuộc gọi 1
    r1 = handle_customer_turn(
        g, "c1", phone, "voice_call", "Cho em hỏi máy lọc không khí giá bao nhiêu, phòng 25m2 ngân sách 5tr"
    )
    handle_customer_turn(g, "c1", phone, "voice_call", "Để em hỏi chồng đã")
    finalize_call(g, "c1")

    # Cuộc gọi 2: Khách hàng cũ quay lại
    r2 = handle_customer_turn(g, "c2", phone, "voice_call", "Alo, chị Hoa đây")
    assert r2["is_returning_customer"] is True
    assert "hôm trước" in r2["final_response"]
    assert "4.890.000" in r2["final_response"]
    assert not any("mấy m2" in x or "ngân sách" in x.lower() for x in [r2["final_response"]])

    # Chốt đơn hàng
    r3 = handle_customer_turn(g, "c2", phone, "voice_call", "Ok vợ chồng chị thống nhất rồi, chị lấy nhé")
    assert r3["call_outcome"] == "chot_don"
    assert "ORD-" in r3["final_response"]


def test_customer_changes_mind_slot_deactivation(test_setup):
    """Khách hàng thay đổi ý kiến: giá trị slot cũ bị hủy kích hoạt (active=0), chỉ còn đúng 1 slot active=1."""
    g = test_setup["graph"]
    phone = test_setup["phone"]
    db_path = test_setup["db_path"]

    r = handle_customer_turn(
        g, "c1", phone, "voice_call", "Cho em hỏi máy lọc không khí giá bao nhiêu, phòng 25m2 ngân sách 5tr"
    )
    handle_customer_turn(g, "c1", phone, "voice_call", "à ngân sách chị chỉ có 4tr thôi")

    prof = load_profile(r["customer_id"])
    assert prof["budget_vnd"] == 4_000_000

    conn = sqlite3.connect(db_path)
    n_active = conn.execute(
        "SELECT COUNT(*) FROM profile WHERE slot='budget_vnd' AND active=1"
    ).fetchone()[0]
    conn.close()
    assert n_active == 1, "Chỉ được phép có duy nhất 1 dòng active=1 cho cùng một slot!"


def test_guardrail_price_hallucination_retry(test_setup):
    """Guardrail phát hiện giá bịa đặt (hallucination), kích hoạt retry và phản hồi giá chính xác."""
    g = test_setup["graph"]
    llm._FAKE_BAD_PRICE_ONCE = True
    try:
        r = handle_customer_turn(
            g, "c3", "0911222333", "voice_call", "Cho em hỏi giá máy lọc không khí"
        )
        assert "4.890.000" in r["final_response"]
        assert r["retry_count"] == 1
    finally:
        llm._FAKE_BAD_PRICE_ONCE = False


def test_unknown_question_handoff_and_knowledge_gap(test_setup):
    """Câu hỏi ngoài phạm vi hiểu biết: tự động chuyển máy nhân viên và ghi nhận vào knowledge_gaps."""
    g = test_setup["graph"]
    db_path = test_setup["db_path"]

    r = handle_customer_turn(
        g,
        "c4",
        "0900000001",
        "voice_call",
        "Máy này bảo hành mấy năm và có tương tác với thuốc tiểu đường không?",
    )
    assert r["call_outcome"] == "chuyen_may"
    assert "AI" in r["final_response"]

    conn = sqlite3.connect(db_path)
    gaps = conn.execute("SELECT question FROM knowledge_gaps").fetchall()
    conn.close()
    assert len(gaps) == 1


def test_tool_timeout_triggers_handoff(test_setup):
    """Mô phỏng tool bị timeout: hệ thống xử lý êm đẹp và chuyển máy mà không bị crash cuộc gọi."""
    g = test_setup["graph"]
    orig_catalog = TOOLS["catalog_search"]
    orig_timeout = nodes.TOOL_TIMEOUT_S

    try:
        TOOLS["catalog_search"] = lambda **kw: time.sleep(2)
        nodes.TOOL_TIMEOUT_S = 0.3
        r = handle_customer_turn(
            g, "c5", "0900000002", "voice_call", "Giá máy lọc không khí bao nhiêu"
        )
        assert r["handoff_reason"] == "tool_timeout"
        assert r["call_outcome"] == "chuyen_may"
    finally:
        TOOLS["catalog_search"] = orig_catalog
        nodes.TOOL_TIMEOUT_S = orig_timeout


def test_extract_money_helper():
    """Unit test cho hàm regex trích xuất số tiền tiếng Việt."""
    assert extract_money("giá 4.890.000đ hay 4,89tr, 5 triệu") == [4890000, 4890000, 5000000]
