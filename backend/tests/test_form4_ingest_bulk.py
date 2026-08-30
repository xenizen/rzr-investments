"""Tests for the quarterly form345 bulk backfill (SCRUM-44).

``parse_source`` is pure and covered without a database. The upsert /
supersede behaviour needs PostgreSQL and is skipped when ``DATABASE_URL``
is unset, same as ``test_migrations``.
"""

import csv
import os
import zipfile

import psycopg
import pytest

import migrate
from db import database_url
from form4_ingest.bulk import BulkSourceError, parse_source
from form4_ingest.store import upsert_transactions

# --- fixture builders -------------------------------------------------------

SUBMISSION_COLUMNS = [
    "ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE",
    "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL",
]
OWNER_COLUMNS = ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME"]
TRANS_COLUMNS = [
    "ACCESSION_NUMBER", "NONDERIV_TRANS_SK", "TRANS_DATE",
    "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE",
]


def _write_tsv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(col, "") for col in columns])


def _build_source(tmp_path, submissions, owners, transactions):
    _write_tsv(tmp_path / "SUBMISSION.tsv", SUBMISSION_COLUMNS, submissions)
    _write_tsv(tmp_path / "REPORTINGOWNER.tsv", OWNER_COLUMNS, owners)
    _write_tsv(tmp_path / "NONDERIV_TRANS.tsv", TRANS_COLUMNS, transactions)
    return tmp_path


@pytest.fixture
def sample_source(tmp_path):
    """A form345 directory exercising the keep/skip rules.

    Accessions:
      A1 -- Form 4, one P and one S line (both kept), plus an F line (dropped)
      A2 -- Form 4, joint filing (two owners -> first wins)
      A3 -- Form 4/A amendment (dropped: not document type "4")
      A4 -- Form 4 but blank ticker (dropped)
      A5 -- Form 4, P line with blank shares (dropped) and one good S line
    """
    submissions = [
        {"ACCESSION_NUMBER": "A1", "FILING_DATE": "05-JAN-2026", "DOCUMENT_TYPE": "4",
         "ISSUERCIK": "0000320193", "ISSUERNAME": "Apple Inc.", "ISSUERTRADINGSYMBOL": "aapl"},
        {"ACCESSION_NUMBER": "A2", "FILING_DATE": "06-FEB-2026", "DOCUMENT_TYPE": "4",
         "ISSUERCIK": "0000789019", "ISSUERNAME": "Microsoft Corp", "ISSUERTRADINGSYMBOL": "MSFT"},
        {"ACCESSION_NUMBER": "A3", "FILING_DATE": "07-MAR-2026", "DOCUMENT_TYPE": "4/A",
         "ISSUERCIK": "0001018724", "ISSUERNAME": "Amazon", "ISSUERTRADINGSYMBOL": "AMZN"},
        {"ACCESSION_NUMBER": "A4", "FILING_DATE": "08-MAR-2026", "DOCUMENT_TYPE": "4",
         "ISSUERCIK": "0001", "ISSUERNAME": "Private Co", "ISSUERTRADINGSYMBOL": "NONE"},
        {"ACCESSION_NUMBER": "A5", "FILING_DATE": "09-MAR-2026", "DOCUMENT_TYPE": "4",
         "ISSUERCIK": "0000051143", "ISSUERNAME": "IBM", "ISSUERTRADINGSYMBOL": "IBM"},
    ]
    owners = [
        {"ACCESSION_NUMBER": "A1", "RPTOWNERCIK": "0001214156", "RPTOWNERNAME": "COOK TIMOTHY"},
        {"ACCESSION_NUMBER": "A2", "RPTOWNERCIK": "0001111111", "RPTOWNERNAME": "NADELLA SATYA"},
        {"ACCESSION_NUMBER": "A2", "RPTOWNERCIK": "0002222222", "RPTOWNERNAME": "SECOND OWNER"},
        {"ACCESSION_NUMBER": "A3", "RPTOWNERCIK": "0003333333", "RPTOWNERNAME": "JASSY ANDREW"},
        {"ACCESSION_NUMBER": "A4", "RPTOWNERCIK": "0004444444", "RPTOWNERNAME": "DOE JANE"},
        {"ACCESSION_NUMBER": "A5", "RPTOWNERCIK": "0005555555", "RPTOWNERNAME": "KRISHNA ARVIND"},
    ]
    transactions = [
        {"ACCESSION_NUMBER": "A1", "NONDERIV_TRANS_SK": "1", "TRANS_DATE": "02-JAN-2026",
         "TRANS_CODE": "P", "TRANS_SHARES": "1000", "TRANS_PRICEPERSHARE": "185.5"},
        {"ACCESSION_NUMBER": "A1", "NONDERIV_TRANS_SK": "2", "TRANS_DATE": "03-JAN-2026",
         "TRANS_CODE": "S", "TRANS_SHARES": "500", "TRANS_PRICEPERSHARE": "190"},
        {"ACCESSION_NUMBER": "A1", "NONDERIV_TRANS_SK": "3", "TRANS_DATE": "03-JAN-2026",
         "TRANS_CODE": "F", "TRANS_SHARES": "42", "TRANS_PRICEPERSHARE": "190"},
        {"ACCESSION_NUMBER": "A2", "NONDERIV_TRANS_SK": "4", "TRANS_DATE": "05-FEB-2026",
         "TRANS_CODE": "P", "TRANS_SHARES": "2000", "TRANS_PRICEPERSHARE": "410.25"},
        {"ACCESSION_NUMBER": "A3", "NONDERIV_TRANS_SK": "5", "TRANS_DATE": "06-MAR-2026",
         "TRANS_CODE": "P", "TRANS_SHARES": "3000", "TRANS_PRICEPERSHARE": "180"},
        {"ACCESSION_NUMBER": "A4", "NONDERIV_TRANS_SK": "6", "TRANS_DATE": "07-MAR-2026",
         "TRANS_CODE": "P", "TRANS_SHARES": "100", "TRANS_PRICEPERSHARE": "5"},
        {"ACCESSION_NUMBER": "A5", "NONDERIV_TRANS_SK": "7", "TRANS_DATE": "08-MAR-2026",
         "TRANS_CODE": "P", "TRANS_SHARES": "", "TRANS_PRICEPERSHARE": "150"},
        {"ACCESSION_NUMBER": "A5", "NONDERIV_TRANS_SK": "8", "TRANS_DATE": "09-MAR-2026",
         "TRANS_CODE": "S", "TRANS_SHARES": "750", "TRANS_PRICEPERSHARE": "151.75"},
    ]
    return _build_source(tmp_path, submissions, owners, transactions)


# --- parse_source ----------------------------------------------------------


def test_parse_source_keeps_only_clean_ps_form4_rows(sample_source):
    records = list(parse_source(sample_source))
    by_sk = {r["trans_sk"]: r for r in records}

    # kept: A1 P, A1 S, A2 P, A5 S
    assert set(by_sk) == {"1", "2", "4", "8"}


def test_parse_source_normalizes_fields(sample_source):
    record = next(r for r in parse_source(sample_source) if r["trans_sk"] == "1")
    assert record == {
        "issuer_ticker": "AAPL",              # upper-cased
        "issuer_cik": "320193",               # zero-padding stripped
        "issuer_name": "Apple Inc.",
        "insider_name": "COOK TIMOTHY",
        "insider_cik": "1214156",
        "transaction_code": "P",
        "transaction_date": "2026-01-02",     # 02-JAN-2026
        "filing_date": "2026-01-05",
        "shares": 1000.0,
        "price": 185.5,
        "accession_no": "A1",
        "trans_sk": "1",
    }


def test_parse_source_uses_first_owner_for_joint_filing(sample_source):
    record = next(r for r in parse_source(sample_source) if r["trans_sk"] == "4")
    assert record["insider_name"] == "NADELLA SATYA"
    assert record["insider_cik"] == "1111111"


def test_parse_source_reads_a_zip(tmp_path, sample_source):
    archive = tmp_path.parent / "q_form345.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name in ("SUBMISSION.tsv", "REPORTINGOWNER.tsv", "NONDERIV_TRANS.tsv"):
            zf.write(sample_source / name, arcname=name)

    assert {r["trans_sk"] for r in parse_source(archive)} == {"1", "2", "4", "8"}


def test_parse_source_rejects_incomplete_source(tmp_path):
    (tmp_path / "SUBMISSION.tsv").write_text("ACCESSION_NUMBER\n")
    with pytest.raises(BulkSourceError):
        list(parse_source(tmp_path))


# --- upsert_transactions (needs PostgreSQL) -------------------------------

pg = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; upsert tests need a live PostgreSQL",
)

TEST_SCHEMA = "bulk_ingest_test"


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


def _rows(conn):
    return conn.execute(
        "SELECT accession_no, trans_sk, source, shares FROM form4_transactions "
        "ORDER BY accession_no, trans_sk"
    ).fetchall()


@pg
def test_upsert_is_idempotent(db_conn, sample_source):
    first = upsert_transactions(db_conn, parse_source(sample_source), "bulk")
    assert first == 4
    baseline = _rows(db_conn)

    upsert_transactions(db_conn, parse_source(sample_source), "bulk")
    assert _rows(db_conn) == baseline


@pg
def test_bulk_load_removes_pre_existing_edgar_rows_for_the_same_filing(db_conn):
    # An edgar row from the nightly job, with a synthesized trans_sk...
    edgar_row = {
        "issuer_ticker": "AAPL", "issuer_cik": "320193", "issuer_name": "Apple Inc.",
        "insider_name": "COOK TIMOTHY", "insider_cik": "1214156",
        "transaction_code": "P", "transaction_date": "2026-01-02",
        "filing_date": "2026-01-05", "shares": 111.0, "price": 185.5,
        "accession_no": "A1", "trans_sk": "0",
    }
    upsert_transactions(db_conn, [edgar_row], "edgar")

    # ...is replaced wholesale when the quarter carrying A1 is backfilled,
    # even though the bulk row's real NONDERIV_TRANS_SK differs.
    bulk_row = dict(edgar_row, shares=1000.0, trans_sk="8938904")
    upsert_transactions(db_conn, [bulk_row], "bulk")

    assert _rows(db_conn) == [("A1", "8938904", "bulk", 1000.0)]
