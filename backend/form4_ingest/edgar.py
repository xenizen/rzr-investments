"""Nightly incremental Form 4 ingest from SEC EDGAR (epic SCRUM-42, SCRUM-45).

The quarterly bulk data set (SCRUM-44) is authoritative but always a
quarter or more behind. This job fills the gap: each night it pulls the
Form 4s filed since the newest one already stored and upserts their
open-market (P/S) transactions with ``source='edgar'``.

This is the only Form 4 XML parser in the codebase. It grew from the old
live-EDGAR request path (``screener_data``, retired in SCRUM-48 once the DB
became authoritative). What it does differently from a naive port, driven
by what the store needs:

* keeps both P and S in one pass (no direction filter);
* keeps every P/S line regardless of transaction date -- the screener's
  month window is applied at query time (SCRUM-46);
* synthesizes ``trans_sk`` from the line's position in the filing's
  market-trade list. SEC's real ``NONDERIV_TRANS_SK`` only exists in the
  bulk data, and bulk/edgar rows for one filing never coexist (see
  ``form4_ingest.store``).
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx
from edgar import get_filings, set_identity
from edgar.exceptions import EdgarError

from form4_ingest.bulk import KEPT_CODES
from form4_ingest.store import upsert_transactions
from form4_ingest.text import clean_cik, clean_ticker, coerce_number

logger = logging.getLogger(__name__)

FORM_TYPE = "4"

# When the table is empty (first run) and no --since is given, look back
# this far. A real first run should use --since to bound the catch-up.
DEFAULT_FALLBACK_DAYS = 7

# Filings parsed per run. Steady state is 1-2 days (~1600 filings); a wider
# window -- the first run after a bulk backfill, or catching up after an
# outage -- is capped so one invocation can't fire tens of thousands of SEC
# fetches. The cap keeps whole filing-days from the oldest end, so
# max(filing_date) advances and successive runs walk the backlog forward.
# Pass max_filings=0 (CLI: --max-filings 0) to lift it for a deliberate
# one-shot catch-up.
MAX_FILINGS_PER_RUN = 4000

# Concurrent filing fetches, with the same CageFS-safe fallback as
# insider_data. edgartools rate-limits SEC requests itself.
MAX_WORKERS = 10

# One filing not parsing must not sink the run.
FILING_ERRORS = (EdgarError, httpx.HTTPError, ValueError, IndexError)

set_identity(os.environ.get("EDGAR_IDENTITY", "enochmgmt.com enzork@gmail.com"))


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def resolve_window(conn, *, today=None, since=None, fallback_days=DEFAULT_FALLBACK_DAYS):
    """Return ``(start, end)`` for the pull.

    ``end`` is ``today``. ``start`` is, in priority order: an explicit
    ``since``; else the newest ``filing_date`` already stored (re-pulled to
    catch filings that landed late that day); else ``today - fallback_days``.
    """
    today = today or date.today()
    if since is not None:
        return since, today
    row = conn.execute("SELECT max(filing_date) FROM form4_transactions").fetchone()
    newest = row[0] if row else None
    start = newest if newest else today - timedelta(days=fallback_days)
    return start, today


def _default_filings(start, end):
    return get_filings(form=FORM_TYPE, filing_date=f"{start.isoformat()}:{end.isoformat()}")


def normalize_filing(filing):
    """Flatten one Form 4 filing into zero or more P/S transaction records
    in the shape ``form4_ingest.store`` and the screener expect. Returns
    ``[]`` for anything that doesn't parse -- one bad filing is not fatal.
    """
    try:
        form4 = filing.obj()
        if not form4:
            return []
        trades = form4.market_trades
        if trades is None or getattr(trades, "empty", True):
            return []

        filing_date = _parse_date(getattr(filing, "filing_date", None))
        issuer = form4.issuer
        ticker = clean_ticker(getattr(issuer, "ticker", ""))
        if not ticker or filing_date is None:
            return []

        owners = list(form4.reporting_owners or [])
        primary = owners[0] if owners else None
        insider_name = form4.insider_name or (getattr(primary, "name", "") if primary else "")
        insider_cik = clean_cik(str(getattr(primary, "cik", "") or "") if primary else "")

        records = []
        for index, row in enumerate(trades.to_dict("records")):
            if row.get("Code") not in KEPT_CODES:
                continue
            transaction_date = _parse_date(row.get("Date"))
            shares = coerce_number(row.get("Shares"))
            if transaction_date is None or shares is None or shares <= 0:
                continue
            records.append(
                {
                    "issuer_ticker": ticker,
                    "issuer_cik": clean_cik(str(getattr(issuer, "cik", "") or "")),
                    "issuer_name": getattr(issuer, "name", "") or "",
                    "insider_name": insider_name,
                    "insider_cik": insider_cik,
                    "transaction_code": row["Code"],
                    "transaction_date": transaction_date.isoformat(),
                    "filing_date": filing_date.isoformat(),
                    "shares": shares,
                    "price": coerce_number(row.get("Price")),
                    "accession_no": filing.accession_no,
                    "trans_sk": str(index),
                }
            )
        return records
    except FILING_ERRORS:
        logger.warning(
            "form4 ingest: skipping unparseable filing %s",
            getattr(filing, "accession_no", "?"),
        )
        return []


def _load_filings(filings, loader):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        return list(executor.map(loader, filings))
    except RuntimeError:
        return [loader(filing) for filing in filings]
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _cap_filings(filings, max_filings):
    """``(kept, total)``. When ``total`` exceeds ``max_filings``, keep the
    oldest filings up to a whole-day boundary near the cap -- never a
    partial day, so ``max(filing_date)`` advances and the next run resumes
    cleanly after the last day kept. ``max_filings`` of 0/None means no cap.
    """
    total = len(filings)
    if not max_filings or total <= max_filings:
        return filings, total
    ordered = sorted(filings, key=lambda filing: filing.filing_date)
    cutoff = ordered[max_filings - 1].filing_date
    kept = [filing for filing in ordered if filing.filing_date <= cutoff]
    return kept, total


def ingest(
    conn,
    *,
    today=None,
    since=None,
    fallback_days=DEFAULT_FALLBACK_DAYS,
    max_filings=MAX_FILINGS_PER_RUN,
    filings_factory=None,
    dry_run=False,
):
    """Pull Form 4s for the resolved window and upsert their P/S rows.

    Returns a summary dict. Runs on ``conn`` without committing -- the
    caller owns the transaction (see ``db.connection``).
    """
    start, end = resolve_window(conn, today=today, since=since, fallback_days=fallback_days)
    logger.info("form4 ingest: window %s .. %s", start, end)

    factory = filings_factory or _default_filings
    filings, in_window = _cap_filings(list(factory(start, end) or []), max_filings)
    if len(filings) < in_window:
        logger.warning(
            "form4 ingest: %d filings in window, parsing the oldest %d; "
            "re-run to continue (or --max-filings 0 for the whole window)",
            in_window, len(filings),
        )
    logger.info("form4 ingest: parsing %d Form 4 filings", len(filings))

    parsed = _load_filings(filings, normalize_filing)
    records = [record for batch in parsed for record in batch]
    logger.info("form4 ingest: %d P/S transaction rows parsed", len(records))

    upserted = 0 if dry_run else upsert_transactions(conn, records, "edgar")
    logger.info(
        "form4 ingest: %d rows upserted%s",
        upserted,
        " (dry run: 0)" if dry_run else "",
    )

    return {
        "window_start": start,
        "window_end": end,
        "filings_in_window": in_window,
        "filings_parsed": len(filings),
        "records_parsed": len(records),
        # Rows sent to the DB. On a re-run over the same window this still
        # counts every row -- they upsert in place, leaving the table
        # unchanged, but the number is not "new rows".
        "rows_upserted": upserted,
    }
