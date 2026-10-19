import json

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from src.graph import nodes as graph_nodes
from src.graph.nodes.input_nodes import resolve_identity_node
from src.memory.working.postgres_store import PostgresMemoryStore
from src.tools import tool_repository


def _create_crm_engine():
    engine = create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_public_schema(connection, _record):
        connection.execute("ATTACH DATABASE ':memory:' AS public")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE public.customer_identities (
                    customer_id TEXT NOT NULL,
                    normalized_value TEXT NOT NULL,
                    is_verified INTEGER NOT NULL,
                    identity_type TEXT NOT NULL,
                    disabled_at TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE public.customers (
                    customer_id TEXT PRIMARY KEY,
                    full_name TEXT,
                    preferred_name TEXT,
                    honorific TEXT,
                    status TEXT NOT NULL,
                    deleted_at TEXT
                )
                """
            )
        )
    return engine


def _insert_crm_customer(engine, customer_id, phone="0912345678", **values):
    customer = {
        "customer_id": customer_id,
        "full_name": values.get("full_name", "Customer Name"),
        "preferred_name": values.get("preferred_name"),
        "honorific": values.get("honorific"),
        "status": values.get("status", "active"),
        "deleted_at": values.get("deleted_at"),
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO public.customers
                    (customer_id, full_name, preferred_name, honorific, status, deleted_at)
                VALUES
                    (:customer_id, :full_name, :preferred_name, :honorific, :status, :deleted_at)
                """
            ),
            customer,
        )
        connection.execute(
            text(
                """
                INSERT INTO public.customer_identities
                    (customer_id, normalized_value, is_verified, identity_type, disabled_at)
                VALUES
                    (:customer_id, :phone, :is_verified, 'phone', NULL)
                """
            ),
            {
                "customer_id": customer_id,
                "phone": phone,
                "is_verified": int(values.get("is_verified", True)),
            },
        )


class TestCRMGetCustomer:
    def test_invalid_phone_returns_not_found_without_query(self, monkeypatch):
        def fail_if_queried():
            raise AssertionError("Invalid phone must not query the CRM database")

        monkeypatch.setattr(tool_repository, "_get_crm_engine", fail_if_queried)

        result = tool_repository.crm_get_customer.invoke({"phone": "123"})

        assert result["found"] is False
        assert result["ambiguous"] is False
        assert result["error"] is None

    def test_valid_phone_with_no_matching_rows_returns_not_found(self, monkeypatch):
        engine = _create_crm_engine()
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)
        try:
            result = tool_repository.crm_get_customer.invoke(
                {"phone": "+84 912-345-678"}
            )
        finally:
            engine.dispose()

        assert result["phone"] == "0912345678"
        assert result["found"] is False
        assert result["customer_id"] is None
        assert result["error"] is None

    def test_one_match_returns_customer_identity(self, monkeypatch):
        engine = _create_crm_engine()
        _insert_crm_customer(
            engine,
            "CUST-1",
            preferred_name="An",
            honorific="Ch",
            is_verified=True,
        )
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)
        try:
            result = tool_repository.crm_get_customer.invoke(
                {"phone": "0912345678"}
            )
        finally:
            engine.dispose()

        assert result["found"] is True
        assert result["customer_id"] == "CUST-1"
        assert result["name"] == "An"
        assert result["honorific"] == "Ch"
        assert result["is_verified"] is True
        assert result["ambiguous"] is False
        assert result["error"] is None

    def test_multiple_customers_with_same_phone_are_ambiguous(self, monkeypatch):
        engine = _create_crm_engine()
        _insert_crm_customer(engine, "CUST-1")
        _insert_crm_customer(engine, "CUST-2")
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)
        try:
            result = tool_repository.crm_get_customer.invoke(
                {"phone": "0912345678"}
            )
        finally:
            engine.dispose()

        assert result["found"] is False
        assert result["customer_id"] is None
        assert result["ambiguous"] is True
        assert result["error"] is None

    @pytest.mark.parametrize("failure_stage", ["engine", "connection"])
    def test_database_failure_is_returned_as_error(self, monkeypatch, failure_stage):
        class FailingEngine:
            def connect(self):
                raise RuntimeError("database unavailable")

        if failure_stage == "engine":
            monkeypatch.setattr(
                tool_repository,
                "_get_crm_engine",
                lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
            )
        else:
            monkeypatch.setattr(
                tool_repository, "_get_crm_engine", lambda: FailingEngine()
            )

        result = tool_repository.crm_get_customer.invoke(
            {"phone": "0912345678"}
        )

        assert result["found"] is False
        assert result["error"] == "database_lookup_failed: RuntimeError"


class TestResolveIdentityNode:
    @staticmethod
    def _state(**overrides):
        state = {
            "messages": [HumanMessage(content="Tư vấn giúp tôi")],
            "customer_id": None,
            "customer_info": {
                "phone": "0912345678",
                "name": "An",
                "_input_text": "Tư vấn giúp tôi",
            },
            "identity_attempts": 0,
            "pending_need": "Tư vấn sản phẩm",
        }
        state.update(overrides)
        return state

    @staticmethod
    def _patch_crm(monkeypatch, result):
        monkeypatch.setattr(
            graph_nodes.input_nodes,
            "crm_get_customer",
            type("FakeCRM", (), {"invoke": staticmethod(lambda _payload: result)})(),
        )

    def test_existing_customer_id_is_reused_without_crm_lookup(self):
        result = resolve_identity_node(
            self._state(customer_id="CUST-1", customer_info={})
        )

        assert result["customer_id"] == "CUST-1"
        assert result["identity_status"] == "resolved"
        assert result["needs_identity"] is False
        assert result["identity_attempts"] == 0
        assert result["pending_need"] == "Tư vấn sản phẩm"

    def test_missing_phone_requests_identity(self):
        result = resolve_identity_node(
            self._state(
                customer_info={"_input_text": "Tư vấn giúp tôi"},
                messages=[HumanMessage(content="Tư vấn giúp tôi")],
                identity_attempts=2,
            )
        )

        assert result["identity_status"] == "needs_input"
        assert result["needs_identity"] is True
        assert result["missing_identity_fields"] == ["phone", "name"]
        assert result["identity_attempts"] == 2

    def test_invalid_phone_does_not_call_crm(self, monkeypatch):
        def fail_if_called(_payload):
            raise AssertionError("Invalid phone must not call the CRM tool")

        monkeypatch.setattr(
            graph_nodes.input_nodes,
            "crm_get_customer",
            type("FakeCRM", (), {"invoke": staticmethod(fail_if_called)})(),
        )
        result = resolve_identity_node(
            self._state(customer_info={"phone": "123", "_input_text": "Tư vấn"})
        )

        assert result["identity_status"] == "invalid_input"
        assert result["needs_identity"] is True
        assert result["identity_attempts"] == 1
        assert result["missing_identity_fields"] == ["phone"]

    @pytest.mark.parametrize(
        ("crm_result", "expected_status", "expected_attempts", "state_overrides"),
        [
            # not_found + name in context (default _state has name='An') -> guest mode, needs_identity=False
            (
                {"found": False},
                "not_found",
                0,  # attempts NOT incremented: guest mode granted immediately
                {},  # default _state() already has name='An'
            ),
            # not_found + NO name -> still needs name, attempts incremented
            (
                {"found": False},
                "not_found",
                1,
                {"customer_info": {"phone": "0912345678", "_input_text": "Tu van"}},
            ),
            ({"ambiguous": True}, "ambiguous", 1, {}),
            # system_error now increments attempts to prevent infinite loops
            (
                {"error": "database_lookup_failed: RuntimeError"},
                "system_error",
                1,  # was 0 before fix; increments so retries eventually exhaust
                {},
            ),
        ],
    )
    def test_crm_failure_states(
        self, monkeypatch, crm_result, expected_status, expected_attempts, state_overrides
    ):
        self._patch_crm(monkeypatch, crm_result)

        result = resolve_identity_node(self._state(**state_overrides))

        assert result["identity_status"] == expected_status
        assert result["identity_attempts"] == expected_attempts

    def test_not_found_with_phone_and_name_proceeds_as_guest(self, monkeypatch):
        """not_found + valid phone + name -> no more identity prompts; guest mode."""
        self._patch_crm(monkeypatch, {"found": False, "ambiguous": False, "error": None})

        result = resolve_identity_node(
            self._state(
                customer_info={"phone": "0912345678", "name": "Kim Truc", "_input_text": "Kim Truc 0912345678"},
            )
        )

        assert result["identity_status"] == "not_found"
        assert result["needs_identity"] is False
        assert result["missing_identity_fields"] == []
        assert result["customer_id"] is None

    def test_not_found_without_name_still_needs_identity(self, monkeypatch):
        """not_found + phone only (no name) -> still ask for name."""
        self._patch_crm(monkeypatch, {"found": False, "ambiguous": False, "error": None})

        result = resolve_identity_node(
            self._state(
                customer_info={"phone": "0912345678", "_input_text": "0912345678"},
            )
        )

        assert result["identity_status"] == "not_found"
        assert result["needs_identity"] is True
        assert "name" in result["missing_identity_fields"]
        assert result["identity_attempts"] == 1

    def test_successful_lookup_resets_identity_attempts(self, monkeypatch):
        self._patch_crm(
            monkeypatch,
            {
                "found": True,
                "customer_id": "CUST-1",
                "name": "An",
                "honorific": None,
                "is_verified": True,
                "ambiguous": False,
                "error": None,
            },
        )

        result = resolve_identity_node(self._state(identity_attempts=3))

        assert result["customer_id"] == "CUST-1"
        assert result["identity_status"] == "resolved"
        assert result["needs_identity"] is False
        assert result["identity_attempts"] == 0
        assert result["missing_identity_fields"] == []


class TestUpdateSessionCustomerId:
    def test_updates_session_and_working_event_identity(self):
        store = PostgresMemoryStore("sqlite+pysqlite:///:memory:")
        try:
            with store.engine.connect() as connection:
                connection.connection.driver_connection.create_function(
                    "now", 0, lambda: "2026-10-18T00:00:00"
                )
                connection.execute(
                    text(
                        """
                        CREATE TABLE conversation_sessions (
                            session_id TEXT PRIMARY KEY,
                            customer_id TEXT,
                            updated_at TEXT
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO conversation_sessions
                            (session_id, customer_id, updated_at)
                        VALUES
                            ('SESSION-1', NULL, 'before'),
                            ('SESSION-2', NULL, 'before')
                        """
                    )
                )
                connection.execute(
                    store.working_events.insert(),
                    [
                        {
                            "event_id": "EVENT-1",
                            "session_id": "SESSION-1",
                            "turn_id": "TURN-1",
                            "turn_number": 1,
                            "customer_id": None,
                            "created_at": "2026-10-18T00:00:00",
                            "payload_json": json.dumps({"identity": {}, "keep": True}),
                        },
                        {
                            "event_id": "EVENT-2",
                            "session_id": "SESSION-2",
                            "turn_id": "TURN-2",
                            "turn_number": 1,
                            "customer_id": None,
                            "created_at": "2026-10-18T00:00:00",
                            "payload_json": json.dumps({"identity": {}}),
                        },
                    ],
                )
                connection.commit()

            store.update_session_customer_id("SESSION-1", "CUST-1")

            with store.engine.connect() as connection:
                session_rows = connection.execute(
                    text(
                        """
                        SELECT session_id, customer_id FROM conversation_sessions
                        ORDER BY session_id
                        """
                    )
                ).mappings().all()
                event_rows = connection.execute(
                    text(
                        """
                        SELECT event_id, session_id, customer_id, payload_json
                        FROM working_events ORDER BY event_id
                        """
                    )
                ).mappings().all()
        finally:
            store.close()

        assert [(row["session_id"], row["customer_id"]) for row in session_rows] == [
            ("SESSION-1", "CUST-1"),
            ("SESSION-2", None),
        ]
        assert event_rows[0]["customer_id"] == "CUST-1"
        assert event_rows[0]["session_id"] == "SESSION-1"
        assert json.loads(event_rows[0]["payload_json"]) == {
            "identity": {"customer_id": "CUST-1"},
            "keep": True,
        }
        assert event_rows[1]["customer_id"] is None
        assert event_rows[1]["session_id"] == "SESSION-2"
        assert json.loads(event_rows[1]["payload_json"]) == {"identity": {}}