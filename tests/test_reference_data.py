from src.api.routers import reference_data


def test_contact_mapping_masks_phone_and_email():
    item = reference_data._customer({
        "customer_id": "C001", "full_name": "Test Customer",
        "phone": "0984726714", "email": "customer@example.test",
    })
    assert item["phone"] == "09•••••714"
    assert item["email"] == "c•••@example.test"
    assert "0984726714" not in str(item)
    assert "customer@example.test" not in str(item)


def test_repository_customer_fallback_is_masked(monkeypatch):
    monkeypatch.setattr(reference_data.tool_repository, "_get_crm_engine", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    response = reference_data.customers(q="C001")
    assert response["source"] == "repository"
    assert len(response["items"]) == 1
    assert "••" in response["items"][0]["phone"]


def test_customer_pagination_and_empty_search(monkeypatch):
    monkeypatch.setattr(reference_data, "_repo_customers", lambda: [{"id": f"C{i}", "name": "Customer", "phone": "masked", "email": "masked"} for i in range(5)])
    monkeypatch.setattr(reference_data.tool_repository, "_get_crm_engine", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    page = reference_data.customers(page=2, page_size=2)
    assert page["total"] == 5
    assert len(page["items"]) == 2
    empty = reference_data.customers(q="no-match")
    assert empty["source"] == "repository"
    assert empty["items"] == []
    assert empty["total"] == 0


def test_successful_empty_customer_query_does_not_use_repository(monkeypatch):
    class EmptyRows:
        def mappings(self): return self
        def all(self): return []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, *_args): return EmptyRows()
    class Engine:
        def connect(self): return Connection()
    monkeypatch.setattr(reference_data.tool_repository, "_get_crm_engine", lambda: Engine())
    response = reference_data.customers()
    assert response["source"] == "backend"
    assert response["items"] == []
    assert response["total"] == 0


def test_promotion_dates_use_reference_date():
    promotions = {item["code"]: item for item in reference_data._repo_promotions()}
    assert promotions["AIR-OCT"]["status"] == "Active"
    assert promotions["11-11"]["status"] == "Upcoming"
    assert reference_data._promotion_status("2026-10-15T08:00:00Z", "2026-10-15") == "Active"


def test_policy_corpus_excludes_internal_documents():
    items = reference_data._repo_policies()
    assert items
    assert all("noi-bo" not in item["id"].lower() for item in items)
    assert all("noi-quy-nhan-vien" not in item["id"].lower() for item in items)
    assert all("playbook-telesale" not in item["id"].lower() for item in items)
    assert all("changelog" not in item["id"].lower() for item in items)
    assert any(item["id"] == "chinh-sach-doi-tra-v2026-06-HET-HIEU-LUC" for item in items)
    assert any(item["status"] == "Archived" for item in items)


def test_policy_endpoint_returns_repository_corpus():
    response = reference_data.policies()
    assert response["source"] == "backend"
    assert response["items"]


def test_products_and_promotions_fall_back_to_repository(monkeypatch):
    monkeypatch.setattr(reference_data.tool_repository, "_get_supabase", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    products = reference_data.products()
    promos = reference_data.promotions()
    assert products["source"] == "repository" and products["items"]
    assert promos["source"] == "repository" and promos["items"]
    assert promos["reference_date"] == "2026-10-15"
