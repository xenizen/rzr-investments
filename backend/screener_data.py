"""SEC Form 4 retrieval and normalization for the Insider-Transaction
Screener (epic SCRUM-29).

This module answers one question: *what open-market insider purchases (or
sales) were just reported to the SEC?* It pulls the most recent market-wide
Form 4 filings, parses each one, and flattens it into a list of
per-transaction records that later stages aggregate (SCRUM-33),
price-filter (SCRUM-34), and paginate (SCRUM-35).

Scope limit -- there is no user-selectable lookback. Like ``insider_data``'s
symbol-less path, a market-wide Form 4 pull is far too large to parse in
full on every request: a single day is ~800 filings, each needing its own
HTTP fetch + XML parse. Only the most recent ``SCAN_LIMIT`` filings inside a
short fixed trailing window are parsed, so in practice the screener only
sees roughly the last day of activity. Historical screening (weeks/months
back) needs a stored, nightly-refreshed Form 4 dataset -- tracked as
SCRUM-42, out of scope here.
"""

import itertools
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx
from edgar import get_filings, set_identity
from edgar.exceptions import EdgarError

FORM_TYPE = "4"

# Form 4 transaction codes we care about: open-market purchase / sale. The
# UI's "Purchase" / "Sold" directions map straight onto these.
DIRECTION_CODES = {"Purchase": "P", "Sold": "S"}
DEFAULT_DIRECTION = "Purchase"

# Trailing window handed to get_filings(). Kept small so get_filings stays
# fast -- it only has to bound the candidate set; SCAN_LIMIT below is what
# actually decides how much gets parsed. A week comfortably contains
# SCAN_LIMIT filings even across weekends/holidays.
LOOKBACK_DAYS = 7

# Most recent filings parsed per request -- see the module docstring.
SCAN_LIMIT = 1000

# One page's worth of filing detail fetches run concurrently when the host
# allows it (see _load_filings) -- mirrors insider_data.MAX_WORKERS.
MAX_WORKERS = 10

# Same "this filing/query didn't work out" set insider_data uses: EdgarError
# for the library (incl. parsing), httpx.HTTPError for network, ValueError
# for bad input, IndexError for filings with malformed ownership XML.
FILING_ERRORS = (EdgarError, httpx.HTTPError, ValueError, IndexError)

# SEC requires a real identifying name/email on every request. insider_data
# sets this at its own import time; set it here too so this module works
# whether or not that one has been imported. Same env override.
set_identity(os.environ.get("EDGAR_IDENTITY", "enochmgmt.com enzork@gmail.com"))


def _default_filings(filing_date_range):
    return get_filings(form=FORM_TYPE, filing_date=filing_date_range)


def _validate_direction(direction):
    code = DIRECTION_CODES.get(direction)
    if code is None:
        raise ValueError(f"direction must be one of {sorted(DIRECTION_CODES)}")
    return code


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _coerce_number(value):
    """Best-effort numeric parse of an edgartools cell.

    Share/price cells are usually already numeric, but can arrive as strings
    with trailing footnote markers ("1000 F1"); take the leading numeric run
    in that case. NaN and unparseable values become ``None``.
    """
    if value is None:
        return None
    if isinstance(value, str):
        digits = "".join(itertools.takewhile(lambda c: c.isdigit() or c == ".", value.strip()))
        try:
            return float(digits) if digits else None
        except ValueError:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _normalize_filing(filing, code, window_start, today):
    """Flatten one Form 4 filing into zero or more transaction records.

    Only non-derivative open-market rows matching ``code`` and whose
    transaction date falls within [window_start, today] are kept. Returns
    ``[]`` for anything that doesn't parse -- one bad filing shouldn't sink
    the whole screen.
    """
    try:
        form4 = filing.obj()
        if not form4:
            return []
        trades = form4.market_trades
        if trades is None or getattr(trades, "empty", True):
            return []

        issuer = form4.issuer
        owners = list(form4.reporting_owners or [])
        primary = owners[0] if owners else None

        records = []
        for row in trades.to_dict("records"):
            if row.get("Code") != code:
                continue
            transaction_date = _parse_date(row.get("Date"))
            if transaction_date is None or not (window_start <= transaction_date <= today):
                continue
            shares = _coerce_number(row.get("Shares"))
            if shares is None:
                continue
            records.append(
                {
                    "issuer_ticker": (getattr(issuer, "ticker", "") or "").upper(),
                    "issuer_cik": str(getattr(issuer, "cik", "") or ""),
                    "issuer_name": getattr(issuer, "name", "") or "",
                    "insider_name": form4.insider_name or (getattr(primary, "name", "") if primary else ""),
                    "insider_cik": str(getattr(primary, "cik", "") or "") if primary else "",
                    "transaction_code": code,
                    "transaction_date": transaction_date.isoformat(),
                    "shares": shares,
                    "price": _coerce_number(row.get("Price")),
                    "filing_date": str(filing.filing_date),
                    "accession_no": filing.accession_no,
                }
            )
        return records
    except FILING_ERRORS:
        return []


def _load_filings(filings, loader):
    """Parse a batch of filings, in parallel when the host allows it.

    Same CageFS-safe fallback as insider_data._load_filings: some shared
    hosts cap threads tightly enough that the pool can't start (a plain
    RuntimeError) -- drop to sequential rather than fail the screen.
    """
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        return list(executor.map(loader, filings))
    except RuntimeError:
        return [loader(filing) for filing in filings]
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def get_insider_transactions(
    direction=DEFAULT_DIRECTION,
    *,
    filings_factory=None,
    today=None,
    lookback_days=LOOKBACK_DAYS,
):
    """Return normalized Form 4 transaction records for the given screen.

    ``direction`` is "Purchase" or "Sold" (mapped to transaction codes P/S).
    There is no lookback parameter -- the screener always reads the most
    recent filings (see the module docstring and SCRUM-42). Each record:

        {issuer_ticker, issuer_cik, issuer_name, insider_name, insider_cik,
         transaction_code, transaction_date, shares, price, filing_date,
         accession_no}

    Records are sorted newest transaction first. Raises ``ValueError`` for a
    bad ``direction`` (SCRUM-36 maps that to a user message).
    """
    code = _validate_direction(direction)
    today = today or date.today()
    window_start = today - timedelta(days=lookback_days)

    factory = filings_factory or _default_filings
    filings = factory(f"{window_start.isoformat()}:{today.isoformat()}")
    if not filings:
        return []

    scanned = sorted(filings[:SCAN_LIMIT], key=lambda f: f.filing_date, reverse=True)
    loaded = _load_filings(scanned, lambda f: _normalize_filing(f, code, window_start, today))

    records = [record for batch in loaded for record in batch]
    records.sort(key=lambda r: r["transaction_date"], reverse=True)
    return records
