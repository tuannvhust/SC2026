"""Database-backed identifiers for customer, order, and conversation records."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _next_number(engine: Engine, sequence: str, connection=None) -> int:
    # Sequence names are constants at call sites; values are atomic in PostgreSQL.
    if connection is not None:
        value = connection.execute(
            text("SELECT nextval(CAST(:sequence_name AS regclass))"),
            {"sequence_name": f"public.{sequence}"},
        ).scalar_one()
        return int(value)
    with engine.begin() as connection:
        value = connection.execute(
            text("SELECT nextval(CAST(:sequence_name AS regclass))"),
            {"sequence_name": f"public.{sequence}"},
        ).scalar_one()
    return int(value)


def next_customer_id(engine: Engine, connection=None) -> str:
    return f"C{_next_number(engine, 'customer_id_seq', connection):03d}"


def next_order_id(engine: Engine, connection=None) -> str:
    return f"OD{_next_number(engine, 'order_id_seq', connection):06d}"


def next_session_id(engine: Engine) -> str:
    return f"S{_next_number(engine, 'session_id_seq'):06d}"


def sync_id_sequences(connection) -> None:
    """Advance PostgreSQL allocators past all existing normalized IDs."""
    for sequence, table, column, pattern in (
        ("customer_id_seq", "customers", "customer_id", r"^C([0-9]+)$"),
        ("order_id_seq", "orders", "order_id", r"^OD([0-9]+)$"),
        ("session_id_seq", "conversation_sessions", "session_id", r"^S([0-9]+)$"),
    ):
        connection.execute(
            text(
                "SELECT setval(CAST(:sequence_name AS regclass), "
                "GREATEST(COALESCE((SELECT MAX(substring(" + column +
                " from :pattern)::bigint) FROM public." + table +
                " WHERE " + column + " ~ :pattern), 1), 1), "
                "COALESCE((SELECT MAX(substring(" + column +
                " from :pattern)::bigint) FROM public." + table +
                " WHERE " + column + " ~ :pattern), 0) > 0)"
            ),
            {"sequence_name": f"public.{sequence}", "pattern": pattern},
        )
