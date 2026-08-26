import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx
from edgar import Company, get_filings
from edgar import set_identity
from edgar.exceptions import EdgarError

NO_CRITERIA_ENTERED = "No Search Criteria Entered"
NO_INSIDER_DATA_FOUND = "No Insider Data Found: Real Stock?"

FORM_TYPE = "4"
PAGE_SIZE = 10
# Raw filings considered per request, before pagination is applied. Without
# this, a symbol-less (name/date-only) search hits SEC-wide get_filings()
# and sorts the entire matching set -- which can be the whole historical
# Form 4 index -- in memory on every request. Filings come back newest-first
# from edgartools already; capping to the first SCAN_LIMIT and *then*
# re-sorting keeps that guarantee explicit without materializing more than
# this many filing objects. A search that would need to look past this many
# candidates to find its matches may come back with fewer results (or none)
# even though more exist further back in SEC's history.
SCAN_LIMIT = 500
# One page's worth of filing detail fetches run concurrently (see
# _load_filing) -- a pool the size of a page is enough to keep every fetch
# in flight at once without unbounded thread growth on a bigger SCAN_LIMIT.
MAX_WORKERS = PAGE_SIZE

# Exceptions that mean "this filing/query didn't work out" rather than a bug
# in this module. EdgarError covers the edgartools library itself (including
# parsing errors), httpx.HTTPError covers network failures, ValueError
# covers bad input, and IndexError covers filings with malformed ownership
# XML (e.g. no <reportingOwner> element -- edgartools indexes into that list
# with no emptiness check).
FILING_ERRORS = (EdgarError, httpx.HTTPError, ValueError, IndexError)

# SEC requires a real identifying name/email on every request. Set once at
# import time -- override via env var so this isn't hardcoded to one
# person's identity.
set_identity(os.environ.get("EDGAR_IDENTITY", "enochmgmt.com enzork@gmail.com"))


def _default_company_factory(symbol):
    return Company(symbol)


def _default_global_filings(filing_date):
    return get_filings(form=FORM_TYPE, filing_date=filing_date)


def _filing_date_range(date_from, date_to):
    """Build a closed filing_date range string for edgartools.

    A one-sided range makes edgartools scan far more of the SEC index than
    intended (it can't narrow to a specific quarter), so the missing side is
    always filled in: a missing date_to defaults to today, a missing
    date_from defaults to the start of date_to's calendar year.
    """
    if date_from and date_to:
        return f"{date_from}:{date_to}"
    if date_from:
        return f"{date_from}:{date.today().isoformat()}"
    if date_to:
        return f"{date_to[:4]}-01-01:{date_to}"
    return None


def _matches_name(name, insider_name, issuer):
    name = name.lower()
    return name in (insider_name or "").lower() or name in (issuer or "").lower()


def _parse_page(page):
    try:
        page = int(page)
    except (TypeError, ValueError):
        return 1
    return page if page >= 1 else 1


def _load_filing(filing):
    """Fetch and parse one filing's ownership summary.

    Returns (filing, summary) on success, or None if the filing has no
    parseable Form 4 content or fails to load. Runs on a worker thread (see
    the ThreadPoolExecutor in get_insider_data) since it's the network I/O
    that dominates a page's latency -- fetching a page's filings serially
    can take several seconds since edgartools doesn't cache filing content
    across distinct Filing instances.
    """
    try:
        form4 = filing.obj()
        if not form4:
            return None
        return filing, form4.get_ownership_summary()
    except FILING_ERRORS:
        # One filing failing to load/parse (a transient SEC hiccup, a
        # malformed document) shouldn't sink the whole page -- skip it and
        # keep going.
        return None


def get_insider_data(
    symbol=None,
    name=None,
    date_from=None,
    date_to=None,
    page=1,
    company_factory=None,
    global_filings_factory=None,
):
    """Look up recent Form 4 insider trading activity from SEC EDGAR.

    `symbol`, `name`, and the `date_from`/`date_to` range are AND'd
    together -- each provided filter narrows the result set. `name` matches
    if it hits either the insider's name or the issuer/company name.

    Results are paginated PAGE_SIZE (10) per page, ordered by filing date
    (most recent first) so pages stay stable across requests, out of at most
    SCAN_LIMIT raw filings considered (see that constant). `total_count` is
    the number of raw Form 4 filings considered (matching symbol/date and
    capped at SCAN_LIMIT), counted *before* the `name` filter -- `name` is
    applied per-page (only the filings on the requested page are checked
    against it), not across the whole set, so a page can come back with
    fewer than PAGE_SIZE results, or even zero, even when `has_next` is
    true. Callers that show `total_count` to a user should caveat it when a
    `name` filter is active, since it doesn't reflect name matches.

    Returns {"results": [...], "page": int, "page_size": int,
    "total_count": int, "has_next": bool} on success, or
    {"error": <message>}.
    """
    symbol = (symbol or "").strip().upper()
    name = (name or "").strip()
    date_from = (date_from or "").strip()
    date_to = (date_to or "").strip()
    page = _parse_page(page)

    if not symbol and not name and not date_from and not date_to:
        return {"error": NO_CRITERIA_ENTERED}

    filing_date = _filing_date_range(date_from, date_to)

    try:
        if symbol:
            factory = company_factory or _default_company_factory
            company = factory(symbol)
            filings = company.get_filings(form=FORM_TYPE, filing_date=filing_date)
        else:
            factory = global_filings_factory or _default_global_filings
            filings = factory(filing_date)
    except FILING_ERRORS:
        return {"error": NO_INSIDER_DATA_FOUND}

    if not filings:
        return {"results": [], "page": page, "page_size": PAGE_SIZE, "total_count": 0, "has_next": False}

    total_count = min(len(filings), SCAN_LIMIT)
    ordered = sorted(filings[:SCAN_LIMIT], key=lambda f: f.filing_date, reverse=True)

    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    has_next = end < total_count

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        loaded = executor.map(_load_filing, ordered[start:end])

    results = []
    for item in loaded:
        if item is None:
            continue
        filing, summary = item
        if name and not _matches_name(name, summary.insider_name, summary.issuer):
            continue
        results.append(
            {
                "insider_name": summary.insider_name,
                "net_change": summary.net_change,
                "issuer": summary.issuer,
                "filing_date": str(filing.filing_date),
            }
        )

    return {
        "results": results,
        "page": page,
        "page_size": PAGE_SIZE,
        "total_count": total_count,
        "has_next": has_next,
    }
