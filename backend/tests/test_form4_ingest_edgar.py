"""Tests for the nightly incremental EDGAR ingest (SCRUM-45).

``resolve_window`` and ``normalize_filing`` are covered with mocks. The
``ingest`` orchestration (and the edgar/bulk supersede rule) needs
PostgreSQL and is skipped when ``DATABASE_URL`` is unset.
"""

import os
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import psycopg
import pytest
from edgar.exceptions import EdgarError

import migrate
from db import database_url
from form4_ingest import edgar
from form4_ingest.store import upsert_transactions


# --- resolve_window -------------------------------------------------------


def _conn_returning(value):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (value,)
    return conn


def test_resolve_window_prefers_explicit_since():
    conn = _conn_returning(date(2026, 6, 30))
    start, end = edgar.resolve_window(
        conn, today=date(2026, 8, 28), since=date(2026, 7, 15)
    )
    assert (start, end) == (date(2026, 7, 15), date(2026, 8, 28))
    conn.execute.assert_not_called()


def test_resolve_window_uses_newest_stored_filing_date():
    conn = _conn_returning(date(2026, 6, 30))
    start, end = edgar.resolve_window(conn, today=date(2026, 8, 28))
    assert (start, end) == (date(2026, 6, 30), date(2026, 8, 28))


def test_resolve_window_falls_back_when_table_is_empty():
    conn = _conn_returning(None)
    start, end = edgar.resolve_window(conn, today=date(2026, 8, 28), fallback_days=7)
    assert (start, end) == (date(2026, 8, 21), date(2026, 8, 28))


# --- _cap_filings ------------------------------------------------------


def _dated(day, n):
    return [MagicMock(filing_date=date(2026, 7, day)) for _ in range(n)]


def test_cap_filings_passes_through_under_the_cap():
    filings = _dated(1, 10) + _dated(2, 10)
    kept, total = edgar._cap_filings(filings, max_filings=100)
    assert (len(kept), total) == (20, 20)


def test_cap_filings_keeps_whole_days_from_the_oldest_end():
    # 3 days x 40 filings; cap 50 -> keep days 1 and 2 whole (80), not a
    # partial day, so the next run resumes cleanly at day 3.
    filings = _dated(3, 40) + _dated(1, 40) + _dated(2, 40)
    kept, total = edgar._cap_filings(filings, max_filings=50)
    assert total == 120
    assert {f.filing_date for f in kept} == {date(2026, 7, 1), date(2026, 7, 2)}


def test_cap_filings_takes_a_single_oversized_day_whole():
    filings = _dated(1, 9000)
    kept, total = edgar._cap_filings(filings, max_filings=4000)
    assert (len(kept), total) == (9000, 9000)  # progress beats the cap


def test_cap_filings_zero_lifts_the_cap():
    filings = _dated(1, 9000)
    kept, _ = edgar._cap_filings(filings, max_filings=0)
    assert len(kept) == 9000


# --- normalize_filing ----------------------------------------------------


def _filing(rows, *, ticker="AAPL", issuer_cik="0000320193", issuer_name="Apple Inc.",
            insider_name="Jane Doe", insider_cik="0001111111",
            filing_date="2026-07-10", accession_no="0000000000-26-000001",
            obj_raises=None):
    filing = MagicMock()
    filing.filing_date = date.fromisoformat(filing_date)
    filing.accession_no = accession_no
    if obj_raises is not None:
        filing.obj.side_effect = obj_raises
        return filing

    form4 = MagicMock()
    form4.market_trades = pd.DataFrame(rows) if rows else pd.DataFrame()
    issuer = MagicMock(ticker=ticker, cik=issuer_cik)
    issuer.name = issuer_name
    form4.issuer = issuer
    form4.insider_name = insider_name
    owner = MagicMock(cik=insider_cik)
    owner.name = insider_name
    form4.reporting_owners = [owner]
    filing.obj.return_value = form4
    return filing


def test_normalize_keeps_p_and_s_and_synthesizes_trans_sk_from_row_position():
    filing = _filing(
        [
            {"Date": "2026-07-08", "Shares": 100, "Price": 1.0, "Code": "A"},   # index 0, dropped
            {"Date": "2026-07-08", "Shares": 200, "Price": 2.0, "Code": "P"},   # index 1
            {"Date": "2026-07-09", "Shares": 300, "Price": 3.0, "Code": "S"},   # index 2
        ]
    )
    records = edgar.normalize_filing(filing)

    assert [(r["transaction_code"], r["trans_sk"], r["shares"]) for r in records] == [
        ("P", "1", 200.0),
        ("S", "2", 300.0),
    ]


def test_normalize_cleans_ticker_and_cik():
    record = edgar.normalize_filing(
        _filing([{"Date": "2026-07-08", "Shares": 10, "Price": 1.0, "Code": "P"}],
                ticker="aapl", issuer_cik="0000320193", insider_cik="0001111111")
    )[0]
    assert record["issuer_ticker"] == "AAPL"
    assert record["issuer_cik"] == "320193"
    assert record["insider_cik"] == "1111111"
    assert record["filing_date"] == "2026-07-10"


def test_normalize_drops_filing_with_no_ticker():
    assert edgar.normalize_filing(
        _filing([{"Date": "2026-07-08", "Shares": 10, "Price": 1.0, "Code": "P"}], ticker="")
    ) == []


def test_normalize_swallows_unparseable_filing():
    assert edgar.normalize_filing(_filing(None, obj_raises=EdgarError("boom"))) == []


# --- ingest (needs PostgreSQL) -----------------------------------------

pg = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; ingest tests need a live PostgreSQL",
)

TEST_SCHEMA = "edgar_ingest_test"


@pytest.fixture
def db_conn():
    setup = psycopg.connect(database_url(), autocommit=True)
    setup.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
    setup.execute(f"CREATE SCHEMA {TEST_SCHEMA}")
    setup.close()

    conn = psycopg.connect(database_url())
    conn.execute(f"SET search_path TO {TEST_SCHEMA}")
    migrate.cmd_up(conn)
    try:
        yield conn
    finally:
        conn.close()
        teardown = psycopg.connect(database_url(), autocommit=True)
        teardown.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
        teardown.close()


def _ingest(conn, filings, **kwargs):
    kwargs.setdefault("since", date(2026, 7, 1))
    kwargs.setdefault("today", date(2026, 7, 31))
    return edgar.ingest(conn, filings_factory=lambda start, end: filings, **kwargs)


def _rows(conn):
    return conn.execute(
        "SELECT accession_no, source, count(*) FROM form4_transactions "
        "GROUP BY accession_no, source ORDER BY accession_no"
    ).fetchall()


@pg
def test_ingest_writes_ps_rows_and_is_idempotent(db_conn):
    filings = [
        _filing([{"Date": "2026-07-08", "Shares": 100, "Price": 1.0, "Code": "P"},
                 {"Date": "2026-07-09", "Shares": 200, "Price": 2.0, "Code": "S"}],
                accession_no="acc-1"),
    ]

    summary = _ingest(db_conn, filings)
    assert summary["records_parsed"] == 2
    assert summary["rows_upserted"] == 2
    baseline = _rows(db_conn)

    _ingest(db_conn, filings)  # same window, same filings
    assert _rows(db_conn) == baseline


@pg
def test_ingest_skips_filings_already_covered_by_bulk(db_conn):
    bulk_row = {
        "issuer_ticker": "AAPL", "issuer_cik": "320193", "issuer_name": "Apple Inc.",
        "insider_name": "COOK TIMOTHY", "insider_cik": "1214156",
        "transaction_code": "P", "transaction_date": "2026-07-02",
        "filing_date": "2026-07-03", "shares": 5000.0, "price": 190.0,
        "accession_no": "acc-bulk", "trans_sk": "42",
    }
    upsert_transactions(db_conn, [bulk_row], "bulk")

    filings = [
        _filing([{"Date": "2026-07-02", "Shares": 9999, "Price": 1.0, "Code": "P"}],
                accession_no="acc-bulk"),
        _filing([{"Date": "2026-07-10", "Shares": 300, "Price": 3.0, "Code": "P"}],
                accession_no="acc-new"),
    ]
    _ingest(db_conn, filings)

    assert _rows(db_conn) == [("acc-bulk", "bulk", 1), ("acc-new", "edgar", 1)]


@pg
def test_reingest_replaces_prior_edgar_rows_even_when_row_order_shifts(db_conn):
    # trans_sk is synthesized from market_trades position, so a filing
    # re-parsed with a different row order gets different keys. The load
    # must still replace the old rows, not stack new ones beside them.
    first = [_filing([{"Date": "2026-07-08", "Shares": 100, "Price": 1.0, "Code": "P"},
                      {"Date": "2026-07-09", "Shares": 200, "Price": 2.0, "Code": "S"}],
                     accession_no="acc-1")]
    _ingest(db_conn, first)

    reordered = [_filing([{"Date": "2026-07-09", "Shares": 200, "Price": 2.0, "Code": "S"},
                          {"Date": "2026-07-08", "Shares": 100, "Price": 1.0, "Code": "P"}],
                         accession_no="acc-1")]
    _ingest(db_conn, reordered)

    total_shares = db_conn.execute(
        "SELECT sum(shares) FROM form4_transactions WHERE accession_no = 'acc-1'"
    ).fetchone()[0]
    assert _rows(db_conn) == [("acc-1", "edgar", 2)]  # 2 rows, not 4
    assert total_shares == 300  # not 600
