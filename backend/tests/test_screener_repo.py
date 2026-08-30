"""Tests for the DB-backed screener source (SCRUM-46).

Validation is covered without a database. The query behaviour needs
PostgreSQL and is skipped when ``DATABASE_URL`` is unset.
"""

import os
from datetime import date

import psycopg
import pytest

import migrate
import screener_repo
from db import database_url
from form4_ingest.store import upsert_transactions
from screener import aggregate_by_issuer

TODAY = date(2026, 8, 28)


# --- validation (no DB) --------------------------------------------------


@pytest.mark.parametrize("bad", ["Hold", "", "buy", None])
def test_invalid_direction_raises(bad):
    with pytest.raises(ValueError):
        screener_repo.get_insider_transactions(bad)


@pytest.mark.parametrize("bad", [0, 7, 12, -1, "lots", None])
def test_invalid_months_raises(bad):
    with pytest.raises(ValueError):
        screener_repo.get_insider_transactions("Purchase", months=bad)


def test_months_ago_clamps_short_months():
    assert screener_repo._months_ago(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert screener_repo._months_ago(date(2026, 1, 15), 1) == date(2025, 12, 15)
    assert screener_repo._months_ago(date(2026, 8, 28), 6) == date(2026, 2, 28)


# --- query behaviour (needs PostgreSQL) -------------------------------

pg = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; screener_repo query tests need PostgreSQL",
)

TEST_SCHEMA = "screener_repo_test"


def _row(**over):
    base = {
        "issuer_ticker": "AAPL", "issuer_cik": "320193", "issuer_name": "Apple Inc.",
        "insider_name": "Jane Doe", "insider_cik": "111", "transaction_code": "P",
        "transaction_date": "2026-08-20", "filing_date": "2026-08-21",
        "shares": 10000.0, "price": 50.0, "accession_no": "a-1", "trans_sk": "0",
    }
    base.update(over)
    return base


@pytest.fixture
def seeded():
    setup = psycopg.connect(database_url(), autocommit=True)
    setup.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
    setup.execute(f"CREATE SCHEMA {TEST_SCHEMA}")
    setup.close()

    conn = psycopg.connect(database_url())
    conn.execute(f"SET search_path TO {TEST_SCHEMA}")
    migrate.cmd_up(conn)

    def seed(rows):
        upsert_transactions(conn, rows, "bulk")

    try:
        yield conn, seed
    finally:
        conn.close()
        teardown = psycopg.connect(database_url(), autocommit=True)
        teardown.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
        teardown.close()


@pg
def test_filters_by_direction(seeded):
    conn, seed = seeded
    seed([
        _row(transaction_code="P", trans_sk="0", accession_no="p"),
        _row(transaction_code="S", trans_sk="1", accession_no="s"),
    ])

    buys = screener_repo.get_insider_transactions("Purchase", months=1, today=TODAY, conn=conn)
    sells = screener_repo.get_insider_transactions("Sold", months=1, today=TODAY, conn=conn)

    assert [r["transaction_code"] for r in buys] == ["P"]
    assert [r["transaction_code"] for r in sells] == ["S"]


@pg
def test_month_window_is_a_transaction_date_lower_bound(seeded):
    conn, seed = seeded
    seed([
        _row(trans_sk="0", accession_no="in", transaction_date="2026-07-29"),   # ~1mo back
        _row(trans_sk="1", accession_no="edge", transaction_date="2026-07-28"),  # exactly 1mo
        _row(trans_sk="2", accession_no="out", transaction_date="2026-07-27"),   # too old
    ])

    got = screener_repo.get_insider_transactions("Purchase", months=1, today=TODAY, conn=conn)

    assert {r["accession_no"] for r in got} == {"in", "edge"}


@pg
def test_orders_newest_transaction_first(seeded):
    conn, seed = seeded
    seed([
        _row(trans_sk="0", accession_no="old", transaction_date="2026-08-01"),
        _row(trans_sk="1", accession_no="new", transaction_date="2026-08-25"),
        _row(trans_sk="2", accession_no="mid", transaction_date="2026-08-10"),
    ])

    got = screener_repo.get_insider_transactions("Purchase", months=2, today=TODAY, conn=conn)

    assert [r["transaction_date"] for r in got] == ["2026-08-25", "2026-08-10", "2026-08-01"]


@pg
def test_record_shape_matches_the_screener_contract(seeded):
    conn, seed = seeded
    seed([_row(price=None, trans_sk="0")])

    (record,) = screener_repo.get_insider_transactions(
        "Purchase", months=1, today=TODAY, conn=conn
    )

    assert set(record) == {
        "issuer_ticker", "issuer_cik", "issuer_name", "insider_name", "insider_cik",
        "transaction_code", "transaction_date", "shares", "price", "filing_date",
        "accession_no",
    }
    assert record["transaction_date"] == "2026-08-20"   # ISO string, not a date
    assert isinstance(record["shares"], float)
    assert record["price"] is None


@pg
def test_output_feeds_aggregate_by_issuer(seeded):
    conn, seed = seeded
    seed([
        _row(trans_sk="0", accession_no="a", insider_cik="c1", shares=10000.0),
        _row(trans_sk="1", accession_no="b", insider_cik="c2", shares=20000.0),
    ])

    records = screener_repo.get_insider_transactions(
        "Purchase", months=1, today=TODAY, conn=conn
    )
    candidates = aggregate_by_issuer(records, 5000)

    assert len(candidates) == 1
    assert candidates[0]["ticker"] == "AAPL"
    assert candidates[0]["total_shares"] == 30000
    assert candidates[0]["multiple_insiders"] is True
