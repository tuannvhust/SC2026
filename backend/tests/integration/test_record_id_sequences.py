from pathlib import Path

from src.memory import ids


class _FakeConnection:
    def __init__(self, value):
        self.value = value

    def execute(self, *_args, **_kwargs):
        return self

    def scalar_one(self):
        return self.value


def test_record_id_formats_are_normalized_and_expand_past_three_digits(monkeypatch):
    values = iter((51, 301178, 4))
    monkeypatch.setattr(ids, "_next_number", lambda *_args: next(values))
    assert ids.next_customer_id(object()) == "C051"
    assert ids.next_order_id(object()) == "OD301178"
    assert ids.next_session_id(object()) == "S000004"
    monkeypatch.setattr(ids, "_next_number", lambda *_args: 1000)
    assert ids.next_customer_id(object()) == "C1000"


def test_seed_keeps_standardized_historical_session_ids():
    project_root = Path(__file__).resolve().parents[3]
    seed_text = (project_root / "data/catalog/crm_seed.json").read_text(encoding="utf-8")
    assert '"session_id": "S000001"' in seed_text
    assert '"session_id": "S000002"' in seed_text
    assert '"session_id": "S000003"' in seed_text
    assert "S-OLD-" not in seed_text


def test_id_migration_preserves_existing_records_and_seeds_from_current_maxima():
    migration = Path(__file__).resolve().parents[2] / "src/memory/migrations/003_record_id_sequences.sql"
    sql = migration.read_text(encoding="utf-8")
    assert "CREATE SEQUENCE IF NOT EXISTS" in sql
    assert "MAX(substring(customer_id" in sql
    assert "MAX(substring(order_id" in sql
    assert "MAX(substring(session_id" in sql
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
