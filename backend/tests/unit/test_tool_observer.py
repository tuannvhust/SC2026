import json
import logging
import pytest
from unittest.mock import Mock
from src.graph.tool_observer import (
    observe_tool,
    observe_tools,
    set_run_context,
    _classify_result,
    _sanitize,
    _sanitize_args,
    _STATUS_SUCCESS,
    _STATUS_EMPTY,
    _STATUS_ERROR,
)

class TestToolObserver:
    """Test suite for structured tool execution logging.

    Requirements:
    1. Tool thành công có kết quả (status=success, result_count > 0).
    2. Tool thành công nhưng rỗng (status=success_empty, result_count=0).
    3. Tool phát sinh exception (status=error, exception captured, re-raised).
    4. Tool trả về dữ liệu lớn (payload truncated/sanitized).
    5. Dữ liệu nhạy cảm được che (phone -> 0***, secret -> ***).
    6. Trạng thái lỗi không bị ghi nhầm thành success.
    7. Tool call được liên kết đúng với run/session/turn.
    """

    def test_tool_success_with_results(self, caplog):
        caplog.set_level(logging.INFO, logger="src.graph.tool_observer")
        set_run_context(run_id="run-101", session_id="sess-abc", turn_id="turn-1")

        tool = Mock()
        tool.name = "catalog.search"
        tool.invoke = Mock(return_value={"items": [{"sku": "SKU-1", "name": "Máy lọc"}]})
        wrapped = observe_tool(tool)

        res = wrapped.invoke({"query": "máy lọc"})
        assert res == {"items": [{"sku": "SKU-1", "name": "Máy lọc"}]}

        log_records = [r for r in caplog.records if r.name == "src.graph.tool_observer"]
        assert len(log_records) >= 1
        msg = log_records[-1].getMessage()
        assert "run=run-101" in msg
        assert "tool=catalog.search" in msg
        assert "status=success" in msg
        assert "results=1" in msg

    def test_tool_success_empty(self, caplog):
        caplog.set_level(logging.INFO, logger="src.graph.tool_observer")
        set_run_context(run_id="run-empty", session_id="sess-xyz")


        tool = Mock()
        tool.name = "catalog.search"
        tool.invoke = Mock(return_value={"items": []})
        wrapped = observe_tool(tool)

        res = wrapped.invoke({"query": "unknown product"})
        assert res == {"items": []}

        log_records = [r for r in caplog.records if r.name == "src.graph.tool_observer"]
        assert len(log_records) >= 1
        msg = log_records[-1].getMessage()
        assert "status=success_empty" in msg
        assert "results=0" in msg

    def test_tool_exception_captured_and_not_logged_as_success(self, caplog):
        caplog.set_level(logging.WARNING, logger="src.graph.tool_observer")
        set_run_context(run_id="run-err")

        tool = Mock()
        tool.name = "pricing.get_quote"
        tool.invoke = Mock(side_effect=RuntimeError("connection timeout"))
        wrapped = observe_tool(tool)

        with pytest.raises(RuntimeError, match="connection timeout"):
            wrapped.invoke({"sku": "SKU-FAIL"})

        log_records = [r for r in caplog.records if r.name == "src.graph.tool_observer"]
        assert len(log_records) >= 1
        msg = log_records[-1].getMessage()
        assert "status=error" in msg
        assert "error=RuntimeError" in msg
        assert "connection timeout" in msg

    def test_tool_error_in_result_classified_as_error(self):
        status, summary, count = _classify_result(
            "catalog.search",
            {"items": [], "status": "error", "error": "Supabase 401 Unauthorized"}
        )
        assert status == _STATUS_ERROR
        assert "Supabase 401" in summary
        assert count == 0

    def test_large_data_sanitization_and_truncation(self):
        large_query = "x" * 1000
        sanitized = _sanitize(large_query, limit=100)
        assert len(sanitized) <= 120
        assert "...(cut)" in sanitized

    def test_sensitive_data_masked(self):
        text = "Khách hàng 0987654321 api_key=secret_xyz123 password=my_pass"
        sanitized = _sanitize(text)
        assert "0***" in sanitized
        assert "0987654321" not in sanitized
        assert "secret_xyz123" not in sanitized
        assert "***" in sanitized

    def test_tool_call_correlation_with_run_and_session(self, caplog):
        caplog.set_level(logging.INFO, logger="src.graph.tool_observer")
        set_run_context(run_id="run-corr-88", session_id="session-trace-99", turn_id="turn-3")

        tool = Mock()
        tool.name = "inventory.check"
        tool.invoke = Mock(return_value={"sku": "SKU-99", "in_stock": True, "qty": 5})
        wrapped = observe_tool(tool)

        wrapped.invoke({"sku": "SKU-99"})
        log_records = [r for r in caplog.records if r.name == "src.graph.tool_observer"]
        msg = log_records[-1].getMessage()
        assert "run=run-corr-88" in msg
        assert "tool=inventory.check" in msg
        assert "status=success" in msg
