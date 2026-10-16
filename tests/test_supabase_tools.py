from types import SimpleNamespace

import httpx
from langchain_core.messages import AIMessage, HumanMessage, messages_to_dict
from pydantic import ValidationError

from src.api.routers import graph_runner
from src.tools import tool_repository
from src.tools.tool_repository import HandoffBrief


class FakeSupabaseQuery:
    def __init__(self, tables, name):
        self.tables = tables
        self.name = name
        self.filters = []
        self.selected = None
        self.row_limit = None

    def select(self, fields):
        self.selected = fields
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def in_(self, field, values):
        self.filters.append((field, set(values)))
        return self

    def limit(self, value):
        self.row_limit = value
        return self

    def execute(self):
        rows = self.tables.get(self.name, [])
        for field, value in self.filters:
            rows = [
                row
                for row in rows
                if (
                    row.get(field) in value
                    if isinstance(value, set)
                    else row.get(field) == value
                )
            ]
        if self.row_limit is not None:
            rows = rows[: self.row_limit]
        return SimpleNamespace(data=rows)


class FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeSupabaseQuery(self.tables, name)


def test_catalog_search_hydrates_semantic_candidates_and_hard_filters(monkeypatch):
    class FakeEngine:
        def search_products(self, query, top_k, category):
            assert query == "máy lọc"
            assert top_k == 30
            return [{"sku": "SKU-1", "name": "Candidate"}]

        def get_by_sku(self, sku):
            return None

    class FakeReranker:
        def rerank(self, query, documents, top_n):
            return documents

    monkeypatch.setattr(
        tool_repository,
        "_get_catalog_components",
        lambda: (FakeEngine(), FakeReranker()),
    )
    monkeypatch.setattr(
        tool_repository,
        "_get_supabase",
        lambda: FakeSupabase(
            {
                "products": [
                    {
                        "sku": "SKU-1",
                        "name": "Live product",
                        "category": "gia-dung/may-loc-khong-khi",
                        "list_price_vnd": 1000,
                        "stock": 5,
                        "attributes": {"room_area_m2": 40},
                    }
                ],
                "product_variants": [
                    {
                        "product_sku": "SKU-1",
                        "variant_sku": "SKU-1-BLACK",
                        "color": "đen",
                        "stock": 2,
                        "price_delta_vnd": 100,
                    }
                ],
            }
        ),
    )

    result = tool_repository.catalog_search.invoke(
        {
            "query": "máy lọc",
            "max_price_vnd": 1100,
            "min_room_area_m2": 30,
        }
    )

    assert result["items"] == [
        {
            "sku": "SKU-1",
            "name": "Live product",
            "category": "gia-dung/may-loc-khong-khi",
            "brand": None,
            "list_price_vnd": 1000,
            "total_stock": 2,
            "in_stock": True,
            "attributes": {"room_area_m2": 40},
            "variants": [
                {
                    "variant_sku": "SKU-1-BLACK",
                    "size": None,
                    "color": "đen",
                    "stock": 2,
                    "price_delta_vnd": 100,
                }
            ],
        }
    ]


def test_live_candidate_filter_applies_inclusive_price_and_stock_bounds(monkeypatch):
    monkeypatch.setattr(
        tool_repository,
        "_get_supabase",
        lambda: FakeSupabase(
            {
                "products": [
                    {"sku": "SKU-1", "list_price_vnd": 4_500_000, "stock": 20},
                    {"sku": "SKU-2", "list_price_vnd": 4_500_000, "stock": 0},
                    {"sku": "SKU-3", "list_price_vnd": 5_000_001, "stock": 3},
                ],
                "product_variants": [
                    {
                        "product_sku": "SKU-1",
                        "variant_sku": "SKU-1-BLUE",
                        "price_delta_vnd": 500_000,
                        "stock": 2,
                    },
                    {
                        "product_sku": "SKU-2",
                        "variant_sku": "SKU-2-BLUE",
                        "price_delta_vnd": 500_000,
                        "stock": 0,
                    },
                ],
            }
        ),
    )

    result = tool_repository.filter_catalog_candidates(
        [{"sku": "SKU-1"}, {"sku": "SKU-2"}, {"sku": "SKU-3"}],
        min_price_vnd=5_000_000,
        max_price_vnd=5_000_000,
        in_stock_only=True,
    )

    assert [item["sku"] for item in result] == ["SKU-1"]
    assert result[0]["matching_price_vnd"] == 5_000_000
    assert result[0]["total_stock"] == 2


def test_inventory_check_reads_variant_stock(monkeypatch):
    monkeypatch.setattr(
        tool_repository,
        "_get_supabase",
        lambda: FakeSupabase(
            {
                "product_variants": [
                    {"variant_sku": "SKU-1-42", "stock": 0, "size": 42}
                ]
            }
        ),
    )

    result = tool_repository.inventory_check.invoke({"sku": "SKU-1-42"})

    assert result["sku"] == "SKU-1-42"
    assert result["in_stock"] is False
    assert result["qty"] == 0


def test_pricing_quote_classifies_expired_and_applied_promotions(monkeypatch):
    monkeypatch.setattr(
        tool_repository,
        "_get_supabase",
        lambda: FakeSupabase(
            {
                "product_variants": [],
                "products": [
                    {
                        "sku": "SKU-AP-PRO",
                        "category": "gia-dung/may-loc-khong-khi",
                        "list_price_vnd": 7_990_000,
                    }
                ],
                "promotions": [
                    {
                        "promo_code": "AIR-OCT",
                        "applies_to": ["SKU-AP-PRO"],
                        "type": "fixed",
                        "discount_vnd": 300_000,
                        "start_date": "2026-10-05",
                        "end_date": "2026-10-30",
                        "stackable": False,
                    },
                    {
                        "promo_code": "AP-SEP",
                        "applies_to": ["SKU-AP-PRO"],
                        "type": "fixed",
                        "discount_vnd": 500_000,
                        "start_date": "2026-08-31",
                        "end_date": "2026-09-30",
                        "stackable": False,
                    },
                    {
                        "promo_code": "MIN-ORDER",
                        "applies_to": ["category:gia-dung"],
                        "type": "fixed",
                        "discount_vnd": 200_000,
                        "start_date": "2026-10-01",
                        "end_date": "2026-10-31",
                        "min_order_vnd": 10_000_000,
                        "stackable": False,
                    },
                ],
            }
        ),
    )

    result = tool_repository.pricing_get_quote.invoke(
        {"sku": "SKU-AP-PRO", "on": "2026-10-09"}
    )

    assert result["sku"] == "SKU-AP-PRO"
    assert result["list_price_vnd"] == 7_990_000
    assert result["final_price_vnd"] == 7_690_000
    assert result["applied_promos"] == ["AIR-OCT"]
    assert result["expired_promos"] == ["AP-SEP"]
    assert result["ineligible_promos"] == [
        {"promo_code": "MIN-ORDER", "reason": "minimum_order_vnd:10000000"}
    ]
    assert result["gifts"] == []
    assert result["freeship"] is False


def test_graph_runner_restores_session_messages_and_passes_context(monkeypatch):
    previous = [HumanMessage(content="Previous question"), AIMessage(content="Previous reply")]
    captured = {}
    monkeypatch.setattr(
        graph_runner,
        "get_postgres_memory_store",
        lambda: SimpleNamespace(
            get_session_events=lambda _session_id: [
                {"payload": {"messages": messages_to_dict(previous)}}
            ]
        ),
    )

    def invoke(state):
        captured.update(state)
        return {
            **state,
            "messages": [*state["messages"], AIMessage(content="Answer.")],
            "turn_number": 2,
        }

    monkeypatch.setattr(
        graph_runner,
        "graph",
        SimpleNamespace(invoke=invoke),
    )

    state = graph_runner.invoke_customer_turn(
        customer_id="customer-1",
        session_id="session-1",
        turn_id="turn-2",
        message="Current question",
        channel="chat",
        customer_info={"phone": "0901234567"},
    )

    assert [message.content for message in captured["messages"]] == [
        "Previous question",
        "Previous reply",
        "Current question",
    ]
    assert captured["customer_id"] == "customer-1"
    assert captured["customer_info"]["channel"] == "web_chat"
    assert state["messages"][-1].content == "Answer."
    assert graph_runner.response_from_graph(state)["reply"] == "Answer."


def test_supabase_client_derives_project_url_from_direct_database_url(monkeypatch):
    created = {}
    client = object()

    def create_client(url, key, options):
        created.update(url=url, key=key, options=options)
        return client

    monkeypatch.setattr(tool_repository, "supabase", None)
    monkeypatch.setattr(tool_repository, "create_client", create_client)
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv(
        "SUPABASE_DATABASE_URL",
        "postgresql://user:password@db.project123.supabase.co:5432/postgres",
    )
    monkeypatch.setenv("SUPABASE_KEY", "test-api-key")

    assert tool_repository._get_supabase() is client
    assert created["url"] == "https://project123.supabase.co"
    assert created["key"] == "test-api-key"
    timeout = created["options"].postgrest_client_timeout
    assert timeout.read == tool_repository.SUPABASE_POSTGREST_TIMEOUT_SECONDS
    assert timeout.connect == 5.0


def test_supabase_query_retries_transient_transport_errors(monkeypatch):
    class UnstableQuery:
        def __init__(self):
            self.attempts = 0

        def execute(self):
            self.attempts += 1
            if self.attempts < 3:
                raise httpx.RemoteProtocolError("Server disconnected")
            return "response"

    delays = []
    monkeypatch.setattr(tool_repository.time, "sleep", delays.append)
    query = UnstableQuery()

    assert tool_repository._execute_supabase_query(query) == "response"
    assert query.attempts == 3
    assert delays == [0.25, 0.5]


def test_supabase_query_does_not_retry_api_or_application_errors(monkeypatch):
    class FailingQuery:
        attempts = 0

        def execute(self):
            self.attempts += 1
            raise RuntimeError("Supabase API error")

    query = FailingQuery()
    monkeypatch.setattr(
        tool_repository.time,
        "sleep",
        lambda _delay: (_ for _ in ()).throw(AssertionError("unexpected retry")),
    )

    try:
        tool_repository._execute_supabase_query(query)
    except RuntimeError as exc:
        assert str(exc) == "Supabase API error"
    else:
        raise AssertionError("Expected Supabase API error.")
    assert query.attempts == 1


def test_handoff_confirmed_facts_requires_an_object():
    schema = HandoffBrief.model_json_schema()
    assert schema["properties"]["facts_confirmed"]["type"] == "object"
    assert "not a string" in schema["properties"]["facts_confirmed"]["description"]

    brief_data = {
        "customer_phone": "0912345678",
        "customer_name": None,
        "escalation_reason": "ngoai_pham_vi_tai_lieu",
        "conversation_summary": "Customer needs further product assistance.",
        "product_advised": None,
        "price_quoted_vnd": None,
        "facts_confirmed": {"max_price": "5000000"},
        "next_action": "Contact customer and continue assistance.",
        "generated_at": "2026-10-09T22:00:00+07:00",
    }
    assert HandoffBrief.model_validate(brief_data).facts_confirmed == {
        "max_price": "5000000"
    }

    brief_data["facts_confirmed"] = '{"max_price": "5000000"}'
    try:
        HandoffBrief.model_validate(brief_data)
    except ValidationError:
        pass
    else:
        raise AssertionError("Serialized JSON string must not validate as an object.")
