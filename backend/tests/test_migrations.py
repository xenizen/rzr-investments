"""Migration-runner tests (SCRUM-43).

These need a live PostgreSQL and are skipped when ``DATABASE_URL`` is unset,
matching how ``conftest`` treats the other integration-touching tests. Each
test runs inside a throwaway schema that the fixture drops afterwards, so
the real ``public`` schema and its ``schema_migrations`` state are never
touched.
"""

import os

import psycopg
import pytest

import migrate
from db import database_url

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; migration tests need a live PostgreSQL",
)

TEST_SCHEMA = "migration_test"


@pytest.fixture
def conn():
    setup = psycopg.connect(database_url(), autocommit=True)
    setup.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
    setup.execute(f"CREATE SCHEMA {TEST_SCHEMA}")
    setup.close()

    c = psycopg.connect(database_url())
    c.execute(f"SET search_path TO {TEST_SCHEMA}")
    try:
        yield c
    finally:
        c.close()
        teardown = psycopg.connect(database_url(), autocommit=True)
        teardown.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
        teardown.close()


def _regclass(conn, name):
    return conn.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0]


def test_up_creates_table_and_indexes(conn):
    migrate.cmd_up(conn)

    assert _regclass(conn, f"{TEST_SCHEMA}.form4_transactions") is not None

    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = %s AND tablename = 'form4_transactions'",
            (TEST_SCHEMA,),
        ).fetchall()
    }
    assert "form4_transactions_ticker_date_idx" in indexes
    assert "form4_transactions_code_date_idx" in indexes
    # The UNIQUE natural key is backed by an index of the same name.
    assert "form4_transactions_natural_key" in indexes

    assert "0001_form4_transactions" in migrate._applied_versions(conn)


def test_down_drops_the_table(conn):
    migrate.cmd_up(conn)
    migrate.cmd_down(conn)

    assert _regclass(conn, f"{TEST_SCHEMA}.form4_transactions") is None
    assert migrate._applied_versions(conn) == []


def test_up_is_idempotent(conn):
    migrate.cmd_up(conn)
    migrate.cmd_up(conn)  # nothing pending the second time -- must not raise

    count = conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version = '0001_form4_transactions'"
    ).fetchone()[0]
    assert count == 1


def test_transaction_code_is_constrained_to_p_or_s(conn):
    migrate.cmd_up(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO form4_transactions
                (issuer_ticker, issuer_cik, transaction_code, transaction_date,
                 filing_date, shares, accession_no, trans_sk, source)
            VALUES ('AAPL', '320193', 'X', '2026-01-02', '2026-01-03', 100,
                    '0000320193-26-000001', '1', 'bulk')
            """
        )


def test_natural_key_rejects_duplicate_lines(conn):
    migrate.cmd_up(conn)
    row = """
        INSERT INTO form4_transactions
            (issuer_ticker, issuer_cik, transaction_code, transaction_date,
             filing_date, shares, accession_no, trans_sk, source)
        VALUES ('AAPL', '320193', 'P', '2026-01-02', '2026-01-03', 100,
                '0000320193-26-000001', '1', %s)
    """
    conn.execute(row, ("bulk",))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(row, ("edgar",))
