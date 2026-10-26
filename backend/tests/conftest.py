import pytest

from src.graph.nodes import input_nodes


@pytest.fixture(autouse=True)
def prevent_unmocked_customer_registration(monkeypatch):
    """Unit tests must explicitly mock registration instead of writing to Supabase."""

    def fail_if_unmocked(**kwargs):
        raise AssertionError(
            "Unexpected CRM registration in a unit test. "
            "Mock input_nodes.crm_create_customer_if_absent explicitly."
        )

    monkeypatch.setattr(
        input_nodes,
        "crm_create_customer_if_absent",
        fail_if_unmocked,
    )