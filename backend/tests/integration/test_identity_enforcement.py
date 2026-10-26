import pytest
from unittest.mock import Mock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from src.graph.builder import build_graph, route_after_call_brief, route_after_identity
from src.graph.nodes.input_nodes import (
    resolve_identity_node,
    request_identity_node,
    build_call_brief_node,
    MAX_IDENTITY_ATTEMPTS,
)
from src.graph.nodes.planner import plan_step_node
from src.graph.state import AgentState


class TestIdentityEnforcement:
    """Test suite for identity enforcement in LangGraph.

    Requirements:
    1. Chưa có số điện thoại: bot hỏi số điện thoại.
    2. Lượt sau hỏi sản phẩm nhưng chưa cung cấp số: bot tiếp tục yêu cầu số, không gọi catalog.
    3. Cung cấp số hợp lệ: chạy nhánh xác minh.
    4. Số không hợp lệ: yêu cầu nhập lại.
    5. Hai người dùng chung số: không tự động gộp danh tính.
    """

    def test_missing_phone_asks_for_phone(self):
        """1. Chưa có số điện thoại: bot hỏi số điện thoại."""
        state: AgentState = {
            "messages": [HumanMessage(content="Tư vấn cho Loan máy lọc không khí")],
            "customer_id": None,
            "customer_info": {"_input_text": "Tư vấn cho Loan máy lọc không khí"},
            "identity_attempts": 0,
        }
        res_identity = resolve_identity_node(state)
        state.update(res_identity)

        assert res_identity["needs_identity"] is True
        assert res_identity["customer_id"] is None
        assert res_identity["identity_status"] == "needs_input"
        assert "phone" in res_identity["missing_identity_fields"]

        route = route_after_identity(state)
        assert route == "request_identity"

        req_res = request_identity_node(state)
        assert len(req_res["messages"]) == 1
        reply = req_res["messages"][0].content
        assert "số điện thoại" in reply

    def test_subsequent_turn_asks_for_phone_and_blocks_catalog(self):
        """2. Lượt sau hỏi sản phẩm nhưng chưa cung cấp số: bot tiếp tục yêu cầu số, không gọi catalog."""
        # Simulated Turn 2 where user still hasn't provided phone
        state: AgentState = {
            "messages": [
                HumanMessage(content="Tư vấn cho Loan máy lọc không khí"),
                AIMessage(content="Dạ mình cho em xin số điện thoại nhé ạ?"),
                HumanMessage(content="Loan muốn xem mẫu lọc bụi mịn"),
            ],
            "customer_id": None,
            "customer_info": {"_input_text": "Loan muốn xem mẫu lọc bụi mịn"},
            "identity_attempts": 1,
            "needs_identity": True,
            "missing_identity_fields": ["phone", "name"],
            "pending_need": "Tư vấn cho Loan máy lọc không khí",
        }

        res_identity = resolve_identity_node(state)
        state.update(res_identity)
        assert res_identity["needs_identity"] is True
        assert res_identity["customer_id"] is None

        # Route check
        assert route_after_identity(state) == "request_identity"

        # Hard guard in plan_step_node check: even if graph somehow routed to plan_step,
        # plan_step_node MUST NOT call LLM or catalog.search
        plan_res = plan_step_node(state)
        assert len(plan_res["messages"]) == 1
        msg = plan_res["messages"][0]
        # Must not contain tool_calls
        assert not getattr(msg, "tool_calls", None)
        assert "số điện thoại" in msg.content

    def test_valid_phone_runs_verification(self, monkeypatch):
        """3. Cung cấp số hợp lệ: chạy nhánh xác minh."""
        def fake_crm_lookup(payload):
            phone = payload.get("phone")
            if phone == "0912345678":
                return {
                    "found": True,
                    "customer_id": "CUST-VERIFIED-1",
                    "name": "Chị Loan",
                    "phone": "0912345678",
                    "is_verified": True,
                    "ambiguous": False,
                    "error": None,
                }
            return {"found": False, "ambiguous": False}

        from src.graph.nodes import input_nodes
        monkeypatch.setattr(
            input_nodes,
            "crm_get_customer",
            type("FakeCRM", (), {"invoke": staticmethod(fake_crm_lookup)})(),
        )

        state: AgentState = {
            "messages": [HumanMessage(content="Số của mình là 0912345678, mình là Loan")],
            "customer_id": None,
            "customer_info": {"_input_text": "Số của mình là 0912345678, mình là Loan"},
            "identity_attempts": 1,
            "needs_identity": True,
        }

        res_identity = resolve_identity_node(state)
        assert res_identity["customer_id"] == "CUST-VERIFIED-1"
        assert res_identity["identity_status"] == "resolved"
        assert res_identity["needs_identity"] is False
        state.update(res_identity)

        route = route_after_identity(state)
        assert route == "build_call_brief"

    def test_invalid_phone_prompts_reentry(self):
        """4. Số không hợp lệ: yêu cầu nhập lại."""
        state: AgentState = {
            "messages": [HumanMessage(content="SĐT của tôi là 12345")],
            "customer_id": None,
            "customer_info": {"phone": "12345", "_input_text": "SĐT của tôi là 12345"},
            "identity_attempts": 0,
        }

        res_identity = resolve_identity_node(state)
        assert res_identity["needs_identity"] is True
        assert res_identity["customer_id"] is None
        assert res_identity["identity_status"] == "invalid_input"
        state.update(res_identity)

        assert route_after_identity(state) == "request_identity"
        req_res = request_identity_node(state)
        assert "số điện thoại" in req_res["messages"][0].content

    def test_two_people_same_phone_not_merged_ambiguous(self, monkeypatch):
        """5. Hai người dùng chung số: không tự động gộp danh tính."""
        def fake_crm_ambiguous(payload):
            return {
                "found": False,
                "customer_id": None,
                "name": None,
                "phone": payload.get("phone"),
                "is_verified": True,
                "ambiguous": True,
                "error": None,
            }

        from src.graph.nodes import input_nodes
        monkeypatch.setattr(
            input_nodes,
            "crm_get_customer",
            type("FakeCRM", (), {"invoke": staticmethod(fake_crm_ambiguous)})(),
        )

        state: AgentState = {
            "messages": [HumanMessage(content="Số mình là 0912345678")],
            "customer_id": None,
            "customer_info": {"_input_text": "Số mình là 0912345678"},
            "identity_attempts": 0,
        }

        res_identity = resolve_identity_node(state)
        assert res_identity["needs_identity"] is True
        assert res_identity["customer_id"] is None
        assert res_identity["identity_status"] == "ambiguous"
        state.update(res_identity)

        # Graph must ask for disambiguation, NOT proceed to plan_step
        assert route_after_identity(state) == "request_identity"
        req_res = request_identity_node(state)
        assert "dùng chung" in req_res["messages"][0].content or "họ tên" in req_res["messages"][0].content

