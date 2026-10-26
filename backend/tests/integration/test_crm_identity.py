"""Unit tests for CRM lookup, customer registration, and identity resolution.

All database-backed CRM tests use an isolated in-memory SQLite fixture. The
identity-node tests fail closed if an unexpected registration reaches the node,
so they cannot accidentally write to the configured Supabase database.
"""

import json

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from src.graph.builder import route_after_identity
from src.graph.nodes import input_nodes
from src.graph.nodes.input_nodes import resolve_identity_node
from src.memory.working.postgres_store import PostgresMemoryStore
from src.tools import tool_repository


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def block_unmocked_node_registration(monkeypatch):
    """Prevent identity-node tests from accidentally registering in real CRM."""

    def fail_if_unmocked(**_kwargs):
        raise AssertionError(
            "Unexpected customer registration from an identity-node test. "
            "Mock input_nodes.crm_create_customer_if_absent explicitly."
        )

    monkeypatch.setattr(
        input_nodes,
        "crm_create_customer_if_absent",
        fail_if_unmocked,
    )


def _create_crm_engine():
    """Create an isolated SQLite database with the columns CRM code uses."""
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
                CREATE TABLE public.customers (
                    customer_id TEXT PRIMARY KEY,
                    full_name TEXT,
                    preferred_name TEXT,
                    honorific TEXT,
                    phone TEXT,
                    phone_verified INTEGER NOT NULL DEFAULT 0,
                    zalo_id TEXT,
                    fb_id TEXT,
                    email TEXT,
                    status TEXT NOT NULL,
                    source TEXT,
                    created_at TEXT,
                    updated_at TEXT,
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
        "phone": phone,
        "phone_verified": int(values.get("is_verified", True)),
        "zalo_id": values.get("zalo_id"),
        "fb_id": values.get("fb_id"),
        "email": values.get("email"),
        "status": values.get("status", "active"),
        "source": values.get("source", "test"),
        "created_at": values.get("created_at", "2026-10-01T00:00:00"),
        "updated_at": values.get("updated_at", "2026-10-01T00:00:00"),
        "deleted_at": values.get("deleted_at"),
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO public.customers (
                    customer_id, full_name, preferred_name, honorific,
                    phone, phone_verified, zalo_id, fb_id, email, status,
                    source, created_at, updated_at, deleted_at
                ) VALUES (
                    :customer_id, :full_name, :preferred_name, :honorific,
                    :phone, :phone_verified, :zalo_id, :fb_id, :email, :status,
                    :source, :created_at, :updated_at, :deleted_at
                )
                """
            ),
            customer,
        )


def _fake_crm(result):
    """Return an object matching the crm_get_customer.invoke interface."""
    return type(
        "FakeCRM",
        (),
        {"invoke": staticmethod(lambda _payload: dict(result))},
    )()


# ---------------------------------------------------------------------------
# CRM lookup
# ---------------------------------------------------------------------------


class TestCRMGetCustomer:
    def test_invalid_phone_returns_not_found_without_query(self, monkeypatch):
        def fail_if_queried():
            raise AssertionError("Invalid phone must not query CRM")

        monkeypatch.setattr(tool_repository, "_get_crm_engine", fail_if_queried)

        result = tool_repository.crm_get_customer.invoke({"phone": "123"})

        assert result["found"] is False
        assert result["customer_id"] is None
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
        assert result["identity_conflict"] is False
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
        assert result["customer_id"] is None
        assert result["error"] == "database_lookup_failed: RuntimeError"

    def test_lookup_by_zalo_facebook_and_email(self, monkeypatch):
        engine = _create_crm_engine()
        _insert_crm_customer(
            engine,
            "CUST-Z",
            phone="0900000001",
            zalo_id="zalo_a",
            fb_id="fb.a",
            email="A@Example.com",
        )
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)
        try:
            by_zalo = tool_repository.crm_get_customer.invoke({"zalo_id": "zalo_a"})
            by_fb = tool_repository.crm_get_customer.invoke({"fb_id": "fb.a"})
            by_email = tool_repository.crm_get_customer.invoke(
                {"email": "a@example.COM"}
            )
        finally:
            engine.dispose()

        assert by_zalo["customer_id"] == "CUST-Z"
        assert by_fb["customer_id"] == "CUST-Z"
        assert by_email["customer_id"] == "CUST-Z"

    def test_shared_phone_seed_case_is_ambiguous(self, monkeypatch):
        engine = _create_crm_engine()
        _insert_crm_customer(engine, "C034", phone="0958421083")
        _insert_crm_customer(engine, "C035", phone="0958421083")
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)
        try:
            result = tool_repository.crm_get_customer.invoke(
                {"phone": "0958421083"}
            )
        finally:
            engine.dispose()

        assert result["ambiguous"] is True
        assert result["found"] is False
        assert result["customer_id"] is None

    def test_shared_phone_resolves_with_matching_name(self, monkeypatch):
        engine = _create_crm_engine()
        _insert_crm_customer(
            engine,
            "C034",
            phone="0958421083",
            preferred_name="Loan",
        )
        _insert_crm_customer(
            engine,
            "C035",
            phone="0958421083",
            preferred_name="Dung",
        )
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)

        try:
            result = tool_repository.crm_get_customer.invoke(
                {"phone": "0958421083", "name": " loan "}
            )
        finally:
            engine.dispose()

        assert result["found"] is True
        assert result["customer_id"] == "C034"
        assert result["name"] == "Loan"
        assert result["ambiguous"] is False
        assert result["identity_conflict"] is False

    def test_wrong_name_for_shared_phone_returns_identity_conflict(self, monkeypatch):
        engine = _create_crm_engine()
        _insert_crm_customer(
            engine,
            "C034",
            phone="0958421083",
            preferred_name="Loan",
        )
        _insert_crm_customer(
            engine,
            "C035",
            phone="0958421083",
            preferred_name="Dung",
        )
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)

        try:
            result = tool_repository.crm_get_customer.invoke(
                {"phone": "0958421083", "name": "Mai"}
            )
        finally:
            engine.dispose()

        assert result["found"] is False
        assert result["customer_id"] is None
        assert result["identity_conflict"] is True


# ---------------------------------------------------------------------------
# CRM registration (all database operations use SQLite, never Supabase)
# ---------------------------------------------------------------------------


class TestCRMCreateCustomer:
    def test_invalid_phone_does_not_open_database(self, monkeypatch):
        def fail_if_opened():
            raise AssertionError("Invalid phone must be rejected before DB access")

        monkeypatch.setattr(tool_repository, "_get_crm_engine", fail_if_opened)

        result = tool_repository.crm_create_customer_if_absent(
            phone="123",
            name="Lan",
        )

        assert result["outcome"] == "invalid_input"
        assert result["created"] is False
        assert result["customer_id"] is None

    @pytest.mark.parametrize("name", ["", "   ", "Khách hàng", "khach hang"])
    def test_generic_or_blank_name_is_rejected_before_db_access(
        self, monkeypatch, name
    ):
        def fail_if_opened():
            raise AssertionError("Invalid name must be rejected before DB access")

        monkeypatch.setattr(tool_repository, "_get_crm_engine", fail_if_opened)

        result = tool_repository.crm_create_customer_if_absent(
            phone="0912345678",
            name=name,
        )

        assert result["outcome"] == "invalid_input"
        assert result["created"] is False
        assert result["customer_id"] is None

    def test_creates_provisional_customer_with_unverified_phone(self, monkeypatch):
        engine = _create_crm_engine()
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)
        monkeypatch.setattr(
            tool_repository, "_generate_customer_id", lambda _connection=None: "C051"
        )

        try:
            result = tool_repository.crm_create_customer_if_absent(
                phone="+84 912-345-678",
                name="Nguyễn Lan",
                honorific="Chị",
                source="test",
            )

            with engine.connect() as connection:
                row = connection.execute(
                    text(
                        """
                        SELECT customer_id, full_name, preferred_name, honorific,
                               phone, phone_verified, status, source
                        FROM public.customers
                        WHERE phone = :phone
                        """
                    ),
                    {"phone": "0912345678"},
                ).mappings().one()
        finally:
            engine.dispose()

        assert result["outcome"] == "created"
        assert result["created"] is True
        assert result["customer_id"] == "C051"
        assert result["customer_id"] == row["customer_id"]
        assert row["full_name"] == "Nguyễn Lan"
        assert row["preferred_name"] == "Lan"
        assert row["honorific"] == "Chị"
        assert row["phone"] == "0912345678"
        assert row["phone_verified"] in (False, 0)
        assert row["status"] == "provisional"
        assert row["source"] == "test"

    def test_repeated_registration_reuses_existing_record(self, monkeypatch):
        engine = _create_crm_engine()
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)
        monkeypatch.setattr(
            tool_repository, "_generate_customer_id", lambda _connection=None: "C051"
        )

        try:
            first = tool_repository.crm_create_customer_if_absent(
                phone="0912345678",
                name="Lan",
            )
            second = tool_repository.crm_create_customer_if_absent(
                phone="0912345678",
                name="Lan",
            )
            with engine.connect() as connection:
                count = connection.execute(
                    text(
                        "SELECT COUNT(*) FROM public.customers WHERE phone = :phone"
                    ),
                    {"phone": "0912345678"},
                ).scalar_one()
        finally:
            engine.dispose()

        assert first["outcome"] == "created"
        assert second["outcome"] == "reused"
        assert second["customer_id"] == first["customer_id"]
        assert count == 1

    def test_existing_shared_phone_is_not_registered_again(self, monkeypatch):
        engine = _create_crm_engine()
        _insert_crm_customer(engine, "C034", phone="0958421083", preferred_name="Loan")
        _insert_crm_customer(engine, "C035", phone="0958421083", preferred_name="Dung")
        monkeypatch.setattr(tool_repository, "_get_crm_engine", lambda: engine)

        try:
            result = tool_repository.crm_create_customer_if_absent(
                phone="0958421083",
                name="Loan",
            )
            with engine.connect() as connection:
                count = connection.execute(
                    text(
                        "SELECT COUNT(*) FROM public.customers WHERE phone = :phone"
                    ),
                    {"phone": "0958421083"},
                ).scalar_one()
        finally:
            engine.dispose()

        assert result["outcome"] == "ambiguous"
        assert result["created"] is False
        assert result["customer_id"] is None
        assert count == 2


# ---------------------------------------------------------------------------
# Identity resolution node
# ---------------------------------------------------------------------------


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
        monkeypatch.setattr(input_nodes, "crm_get_customer", _fake_crm(result))

    def test_existing_customer_id_is_reused_without_crm_lookup(self, monkeypatch):
        def fail_if_called(_payload):
            raise AssertionError("Existing customer_id should bypass CRM lookup")

        monkeypatch.setattr(
            input_nodes,
            "crm_get_customer",
            type("FakeCRM", (), {"invoke": staticmethod(fail_if_called)})(),
        )

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
            input_nodes,
            "crm_get_customer",
            type("FakeCRM", (), {"invoke": staticmethod(fail_if_called)})(),
        )
        result = resolve_identity_node(
            self._state(
                customer_info={"phone": "123", "_input_text": "Tư vấn"},
                messages=[HumanMessage(content="Tư vấn")],
            )
        )

        assert result["identity_status"] == "invalid_input"
        assert result["needs_identity"] is True
        assert result["identity_attempts"] == 1
        assert result["missing_identity_fields"] == ["phone"]

    @pytest.mark.parametrize(
        ("crm_result", "expected_status", "expected_attempts", "state_overrides"),
        [
            (
                {"found": False, "ambiguous": False, "error": None},
                "not_found",
                1,
                {
                    "messages": [HumanMessage(content="0912345678")],
                    "customer_info": {
                        "phone": "0912345678",
                        "_input_text": "0912345678",
                    },
                },
            ),
            (
                {"ambiguous": True, "found": False, "error": None},
                "ambiguous",
                1,
                {},
            ),
            (
                {"error": "database_lookup_failed: RuntimeError"},
                "system_error",
                1,
                {},
            ),
            (
                {"identity_conflict": True, "found": False, "error": None},
                "identity_conflict",
                1,
                {},
            ),
        ],
    )
    def test_crm_unresolved_states_do_not_register_customer(
        self,
        monkeypatch,
        crm_result,
        expected_status,
        expected_attempts,
        state_overrides,
    ):
        self._patch_crm(monkeypatch, crm_result)

        # The autouse safety fixture makes any unexpected registration fail.
        result = resolve_identity_node(self._state(**state_overrides))

        assert result["identity_status"] == expected_status
        assert result["identity_attempts"] == expected_attempts
        assert result["customer_id"] is None
        assert result["needs_identity"] is True

    def test_not_found_with_phone_and_name_registers_customer(self, monkeypatch):
        self._patch_crm(
            monkeypatch,
            {
                "found": False,
                "customer_id": None,
                "name": None,
                "phone": "0912345678",
                "ambiguous": False,
                "identity_conflict": False,
                "error": None,
            },
        )
        registration_calls = []
        registration_result = {
            "outcome": "created",
            "found": True,
            "created": True,
            "customer_id": "CUST-NEW-1",
            "name": "Kim Truc",
            "honorific": None,
            "phone": "0912345678",
            "ambiguous": False,
            "error": None,
        }

        def fake_register(**kwargs):
            registration_calls.append(kwargs)
            return dict(registration_result)

        monkeypatch.setattr(
            input_nodes,
            "crm_create_customer_if_absent",
            fake_register,
        )
        state = self._state(
            messages=[HumanMessage(content="Kim Truc, sđt 0912345678")],
            customer_info={
                "phone": "0912345678",
                "name": "Kim Truc",
                "_input_text": "Kim Truc, sđt 0912345678",
                "channel": "web_chat",
            },
        )

        result = resolve_identity_node(state)

        assert result["customer_id"] == "CUST-NEW-1"
        assert result["identity_status"] == "resolved"
        assert result["needs_identity"] is False
        assert result["identity_attempts"] == 0
        assert result["missing_identity_fields"] == []
        assert result["customer_info"]["phone"] == "0912345678"
        assert result["customer_info"]["name"] == "Kim Truc"
        assert len(registration_calls) == 1
        assert registration_calls[0]["phone"] == "0912345678"
        assert registration_calls[0]["name"] == "Kim Truc"
        assert registration_calls[0]["source"] == "application_chat_web_chat"

    def test_registration_system_error_stays_unresolved(self, monkeypatch):
        self._patch_crm(
            monkeypatch,
            {"found": False, "ambiguous": False, "identity_conflict": False, "error": None},
        )
        monkeypatch.setattr(
            input_nodes,
            "crm_create_customer_if_absent",
            lambda **_kwargs: {
                "outcome": "system_error",
                "found": False,
                "created": False,
                "customer_id": None,
                "error": "registration_failed: RuntimeError",
            },
        )

        result = resolve_identity_node(
            self._state(
                messages=[HumanMessage(content="Mình tên An, sđt 0912345678")],
                customer_info={
                    "phone": "0912345678",
                    "name": "An",
                    "_input_text": "Mình tên An, sđt 0912345678",
                },
            )
        )

        assert result["identity_status"] == "system_error"
        assert result["needs_identity"] is True
        assert result["customer_id"] is None

    def test_not_found_without_name_does_not_register(self, monkeypatch):
        self._patch_crm(
            monkeypatch,
            {"found": False, "customer_id": None, "ambiguous": False, "error": None},
        )
        monkeypatch.setattr(
            input_nodes,
            "crm_create_customer_if_absent",
            lambda **_kwargs: pytest.fail("Must not register without a name"),
        )

        result = resolve_identity_node(
            self._state(
                messages=[HumanMessage(content="0912345678")],
                customer_info={
                    "phone": "0912345678",
                    "_input_text": "0912345678",
                },
            )
        )

        assert result["identity_status"] == "not_found"
        assert result["needs_identity"] is True
        assert result["missing_identity_fields"] == ["name"]
        assert result["customer_id"] is None

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
                "identity_conflict": False,
                "error": None,
            },
        )

        result = resolve_identity_node(self._state(identity_attempts=3))

        assert result["customer_id"] == "CUST-1"
        assert result["identity_status"] == "resolved"
        assert result["needs_identity"] is False
        assert result["identity_attempts"] == 0
        assert result["missing_identity_fields"] == []


# ---------------------------------------------------------------------------
# Identity routing
# ---------------------------------------------------------------------------


class TestIdentityRouting:
    def test_resolved_customer_routes_to_call_brief(self):
        assert route_after_identity(
            {
                "customer_id": "CUST-1",
                "needs_identity": False,
                "identity_status": "resolved",
            }
        ) == "build_call_brief"

    def test_system_error_without_customer_id_routes_to_handoff(self):
        assert route_after_identity(
            {
                "customer_id": None,
                "needs_identity": True,
                "identity_status": "system_error",
                "identity_attempts": 1,
            }
        ) == "handoff_to_human"

    def test_ambiguous_identity_requests_clarification_before_limit(self):
        assert route_after_identity(
            {
                "customer_id": None,
                "needs_identity": True,
                "identity_status": "ambiguous",
                "identity_attempts": 1,
            }
        ) == "request_identity"

    def test_ambiguous_identity_hands_off_after_limit(self):
        from src.graph.nodes.input_nodes import MAX_IDENTITY_ATTEMPTS

        assert route_after_identity(
            {
                "customer_id": None,
                "needs_identity": True,
                "identity_status": "identity_conflict",
                "identity_attempts": MAX_IDENTITY_ATTEMPTS,
            }
        ) == "handoff_to_human"


# ---------------------------------------------------------------------------
# Session identity linking
# ---------------------------------------------------------------------------


class TestUpdateSessionCustomerId:
    def test_updates_only_the_target_session_and_its_working_events(self):
        store = PostgresMemoryStore("sqlite+pysqlite:///:memory:")
        try:
            with store.engine.begin() as connection:
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
                    text(
                        """
                        CREATE TABLE working_events (
                            event_id TEXT PRIMARY KEY,
                            session_id TEXT,
                            turn_id TEXT,
                            turn_number INTEGER,
                            customer_id TEXT,
                            created_at TEXT,
                            payload_json TEXT
                        )
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO working_events (
                            event_id, session_id, turn_id, turn_number,
                            customer_id, created_at, payload_json
                        ) VALUES
                            ('EVENT-1', 'SESSION-1', 'TURN-1', 1, NULL,
                             '2026-10-18T00:00:00', :payload1),
                            ('EVENT-2', 'SESSION-2', 'TURN-2', 1, NULL,
                             '2026-10-18T00:00:00', :payload2)
                        """
                    ),
                    {
                        "payload1": json.dumps({"identity": {}, "keep": True}),
                        "payload2": json.dumps({"identity": {}}),
                    },
                )

            store.update_session_customer_id("SESSION-1", "CUST-1")

            with store.engine.connect() as connection:
                session_rows = connection.execute(
                    text(
                        """
                        SELECT session_id, customer_id
                        FROM conversation_sessions
                        ORDER BY session_id
                        """
                    )
                ).mappings().all()
                event_rows = connection.execute(
                    text(
                        """
                        SELECT event_id, session_id, customer_id, payload_json
                        FROM working_events
                        ORDER BY event_id
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
