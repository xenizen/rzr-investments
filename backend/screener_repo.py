"""DB-backed Form 4 transaction source for the Insider-Transaction Screener
(epic SCRUM-29, story SCRUM-46).

The screener's only Form 4 source. Rows come from the
``form4_transactions`` table -- filled by the bulk backfill (SCRUM-44) and
the nightly EDGAR ingest (SCRUM-45) -- so no SEC request happens on the
screener's request path. Output matches the record shape
``screener.aggregate_by_issuer`` (SCRUM-33) and
``screener_pricing.enrich_and_filter`` (SCRUM-34) consume.

(Before SCRUM-48 this replaced a live market-wide EDGAR pull,
``screener_data``, which is now retired.)

Because history is cheap to query, ``get_insider_transactions`` takes a
``months`` lookback (1-6), wired to the UI dropdown in SCRUM-47.
"""

import calendar
from datetime import date

import db

# "Purchase" / "Sold" -> Form 4 transaction code.
DIRECTION_CODES = {"Purchase": "P", "Sold": "S"}
DEFAULT_DIRECTION = "Purchase"

# The UI's "months to review" dropdown (SCRUM-47). Matches the
# ALLOWED_* pattern in screener.py / screener_pricing.py.
ALLOWED_MONTHS = (1, 2, 3, 4, 5, 6)
DEFAULT_MONTHS = 1

_SELECT = """
    SELECT issuer_ticker, issuer_cik, issuer_name,
           insider_name, insider_cik,
           transaction_code, transaction_date, shares, price,
           filing_date, accession_no
    FROM form4_transactions
    WHERE transaction_code = %s
      AND transaction_date >= %s
    ORDER BY transaction_date DESC
"""


def _validate_direction(direction):
    code = DIRECTION_CODES.get(direction)
    if code is None:
        raise ValueError(f"direction must be one of {sorted(DIRECTION_CODES)}")
    return code


def _validate_months(months):
    try:
        value = int(months)
    except (TypeError, ValueError):
        raise ValueError(f"months must be one of {list(ALLOWED_MONTHS)}")
    if value not in ALLOWED_MONTHS:
        raise ValueError(f"months must be one of {list(ALLOWED_MONTHS)}")
    return value


def _months_ago(reference, months):
    """``reference`` shifted back ``months`` calendar months, clamping the
    day to the target month's length (e.g. Mar 31 - 1mo -> Feb 28)."""
    index = reference.year * 12 + (reference.month - 1) - months
    year, month = divmod(index, 12)
    month += 1
    day = min(reference.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _fetch(conn, code, since):
    rows = conn.execute(_SELECT, (code, since)).fetchall()
    return [
        {
            "issuer_ticker": ticker,
            "issuer_cik": issuer_cik,
            "issuer_name": issuer_name,
            "insider_name": insider_name,
            "insider_cik": insider_cik,
            "transaction_code": transaction_code,
            "transaction_date": transaction_date.isoformat(),
            "shares": float(shares),
            "price": None if price is None else float(price),
            "filing_date": filing_date.isoformat(),
            "accession_no": accession_no,
        }
        for (
            ticker, issuer_cik, issuer_name, insider_name, insider_cik,
            transaction_code, transaction_date, shares, price,
            filing_date, accession_no,
        ) in rows
    ]


def get_insider_transactions(
    direction=DEFAULT_DIRECTION, *, months=DEFAULT_MONTHS, today=None, conn=None
):
    """Return normalized Form 4 transaction records from the DB.

    ``direction`` is "Purchase" or "Sold" (mapped to codes P/S).
    ``months`` (1-6) bounds ``transaction_date`` to the trailing window.
    Records are newest transaction first. Each record::

        {issuer_ticker, issuer_cik, issuer_name, insider_name, insider_cik,
         transaction_code, transaction_date, shares, price, filing_date,
         accession_no}

    Raises ``ValueError`` for a bad ``direction`` or ``months`` (SCRUM-36
    maps that to a user-facing message). ``conn`` is injectable for tests;
    when omitted a connection is opened and closed here.
    """
    code = _validate_direction(direction)
    months = _validate_months(months)
    since = _months_ago(today or date.today(), months)

    if conn is not None:
        return _fetch(conn, code, since)
    with db.connection() as owned:
        return _fetch(owned, code, since)
