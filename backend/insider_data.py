import os
from datetime import date

import httpx
from edgar import Company, get_filings
from edgar import set_identity
from edgar.exceptions import EdgarError

NO_CRITERIA_ENTERED = "No Stock Entered"
NO_INSIDER_DATA_FOUND = "No Insider Data Found: Real Stock?"

FORM_TYPE = "4"
# Filings examined (and, after the name filter, returned) per request. Keeps
# latency bounded for broad symbol-less/name-only searches -- without this, a
# request with no symbol can be scanning hundreds of thousands of SEC-wide
# filings. A search that would need more than this many candidates to find
# its matches may come back with fewer results (or none) even though more
# exist further down the list -- `has_more` in the response tells the caller
# whether that's the case. Superseded by real pagination in SCRUM-13.
MAX_RESULTS = 20

# SEC requires a real identifying name/email on every request. Set once at
# import time, same as backend/rzr-get-insider.py -- override via env var so
# this isn't hardcoded to one person's identity.
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


def get_insider_data(
    symbol=None,
    name=None,
    date_from=None,
    date_to=None,
    company_factory=None,
    global_filings_factory=None,
):
    """Look up recent Form 4 insider trading activity from SEC EDGAR.

    `symbol`, `name`, and the `date_from`/`date_to` range are AND'd
    together -- each provided filter narrows the result set. `name` matches
    if it hits either the insider's name or the issuer/company name.

    Returns {"results": [...], "has_more": bool} on success, or
    {"error": <message>}. `has_more` means more candidate filings exist
    beyond the ones examined -- not that they're guaranteed to match `name`.
    """
    symbol = (symbol or "").strip().upper()
    name = (name or "").strip()
    date_from = (date_from or "").strip()
    date_to = (date_to or "").strip()

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
    except (EdgarError, httpx.HTTPError, ValueError):
        return {"error": NO_INSIDER_DATA_FOUND}

    if not filings:
        return {"results": [], "has_more": False}

    has_more = len(filings) > MAX_RESULTS

    results = []
    for filing in filings[:MAX_RESULTS]:
        form4 = filing.obj()
        if not form4:
            continue
        summary = form4.get_ownership_summary()
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

    return {"results": results, "has_more": has_more}
