import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx
from edgar import Company, get_filings, search_filings
from edgar import set_identity
from edgar.exceptions import EdgarError

NO_CRITERIA_ENTERED = "No Search Criteria Entered"
NO_INSIDER_DATA_FOUND = "No Insider Data Found: Real Stock?"

FORM_TYPE = "4"
PAGE_SIZE = 10
# Raw filings considered per request for a symbol/date-only search (no name
# filter), before pagination is applied. Without this, a symbol-less search
# hits SEC-wide get_filings() and sorts the entire matching set -- which can
# be the whole historical Form 4 index -- in memory on every request.
# Filings come back newest-first from edgartools already; capping to the
# first SCAN_LIMIT and *then* re-sorting keeps that guarantee explicit
# without materializing more than this many filing objects. A search that
# would need to look past this many candidates to find its matches may come
# back with fewer results (or none) even though more exist further back in
# SEC's history.
SCAN_LIMIT = 500
# Cap on how many name/issuer matches to fetch for a `name` search (see
# _search_by_name). This is SEC EDGAR full-text search's own maximum
# `limit`, so it isn't a choice we're making -- 100 real matches is already
# far beyond what SCAN_LIMIT-scanning raw filings could reliably surface
# (see the SCRUM-19 bug this replaced: an insider whose most recent filing
# fell outside the most recent SCAN_LIMIT SEC-wide filings was unreachable
# by name search at all).
NAME_SEARCH_LIMIT = 100
# One page's worth of filing detail fetches run concurrently when the host
# allows it (see _load_filings) -- a pool the size of a page is enough to
# keep every fetch in flight at once without unbounded thread growth on a
# bigger SCAN_LIMIT/NAME_SEARCH_LIMIT.
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


def _default_name_search(name, symbol, date_from, date_to):
    return search_filings(
        query=name,
        forms=FORM_TYPE,
        ticker=symbol or None,
        start_date=date_from or None,
        end_date=_clamp_to_today(date_to) or None,
        limit=NAME_SEARCH_LIMIT,
    )


def _clamp_to_today(date_to):
    """A future end_date makes SEC's full-text search return zero results
    (observed directly, not documented -- SEC's index simply has nothing
    past today, and the query doesn't clamp itself). Cap it here so a date
    picker that lets a user pick a future date can't silently zero out
    their search."""
    if date_to and date_to > date.today().isoformat():
        return date.today().isoformat()
    return date_to


def _filing_date_range(date_from, date_to):
    """Build a closed filing_date range string for edgartools.get_filings().

    A one-sided range makes edgartools scan far more of the SEC index than
    intended (it can't narrow to a specific quarter), so the missing side is
    always filled in: a missing date_to defaults to today, a missing
    date_from defaults to the start of date_to's calendar year. Only used
    for the no-`name` path (see get_insider_data) -- search_filings takes
    start_date/end_date directly and doesn't have this quirk.
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
    parseable Form 4 content or fails to load. It's the network I/O here
    that dominates a page's latency -- fetching a page's filings serially
    can take several seconds since edgartools doesn't cache filing content
    across distinct Filing instances (see _load_filings, which runs this
    concurrently when the host allows it).
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


def _load_search_result(result):
    """Resolve one SEC full-text search hit down to a (filing, summary) pair.

    Same contract as _load_filing -- returns None on any failure, including
    the extra get_filing() network call a search result needs before it can
    be treated like a plain Filing.
    """
    try:
        filing = result.get_filing()
    except FILING_ERRORS:
        return None
    return _load_filing(filing)


def _load_filings(items, loader=_load_filing):
    """Load a page's worth of filings/search results, in parallel when the
    host allows it.

    Some shared hosts (e.g. CloudLinux CageFS-limited accounts) cap the
    account's process/thread count tightly enough that even one extra OS
    thread fails to start (a plain RuntimeError from the thread pool, not
    one of FILING_ERRORS) -- fall back to sequential loading rather than
    fail the whole page when that happens.
    """
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        return list(executor.map(loader, items))
    except RuntimeError:
        return [loader(item) for item in items]
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _build_results(loaded, name):
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
    return results


def _search_by_name(symbol, name, date_from, date_to, page, name_search_factory):
    """Search by insider/issuer name via SEC EDGAR's full-text search.

    Unlike the raw-filings path below, this searches SEC's own server-side
    index of filing content -- not a locally-scanned, latency-bounded
    window of raw filings -- so `total_count` here is a real count of
    filings actually matching `name` (up to NAME_SEARCH_LIMIT), not an
    upper bound that predates the name filter. `name` can still land a
    result that only loosely matches SEC's full-text index but not our own
    stricter insider-name-or-issuer check, so _build_results still applies
    that filter as a final pass.
    """
    factory = name_search_factory or _default_name_search
    try:
        search = factory(name, symbol, date_from, date_to)
    except FILING_ERRORS:
        return {"error": NO_INSIDER_DATA_FOUND}

    total_count = min(search.total, NAME_SEARCH_LIMIT) if search else 0
    if not total_count:
        return {"results": [], "page": page, "page_size": PAGE_SIZE, "total_count": 0, "has_next": False}

    matches = list(search.results)[:NAME_SEARCH_LIMIT]
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    has_next = end < total_count

    loaded = _load_filings(matches[start:end], loader=_load_search_result)

    return {
        "results": _build_results(loaded, name),
        "page": page,
        "page_size": PAGE_SIZE,
        "total_count": total_count,
        "has_next": has_next,
    }


def get_insider_data(
    symbol=None,
    name=None,
    date_from=None,
    date_to=None,
    page=1,
    company_factory=None,
    global_filings_factory=None,
    name_search_factory=None,
):
    """Look up recent Form 4 insider trading activity from SEC EDGAR.

    `symbol`, `name`, and the `date_from`/`date_to` range are AND'd
    together -- each provided filter narrows the result set. `name` matches
    if it hits either the insider's name or the issuer/company name.

    When `name` is given, the search runs through SEC EDGAR's full-text
    search index (scoped by `symbol`/date range if also given), since the
    insider's name generally isn't in the raw filing metadata edgartools
    exposes -- only in each filing's content. This also means `total_count`
    is an accurate count of name matches (capped at NAME_SEARCH_LIMIT), not
    an upper bound that predates filtering.

    Without `name`, results come from the raw filings list for the given
    symbol/date range (or SEC-wide, if neither is given), paginated
    PAGE_SIZE (10) per page and ordered by filing date (most recent first)
    out of at most SCAN_LIMIT raw filings considered (see that constant).

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

    if name:
        return _search_by_name(symbol, name, date_from, date_to, page, name_search_factory)

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

    loaded = _load_filings(ordered[start:end])

    return {
        "results": _build_results(loaded, None),
        "page": page,
        "page_size": PAGE_SIZE,
        "total_count": total_count,
        "has_next": has_next,
    }
