import os

import httpx
from edgar import Company
from edgar import set_identity
from edgar.exceptions import EdgarError

NO_SYMBOL_ENTERED = "No Stock Entered"
NO_INSIDER_DATA_FOUND = "No Insider Data Found: Real Stock?"

FORM_TYPE = "4"
MAX_FILINGS = 20

# SEC requires a real identifying name/email on every request. Set once at
# import time, same as backend/rzr-get-insider.py -- override via env var so
# this isn't hardcoded to one person's identity.
set_identity(os.environ.get("EDGAR_IDENTITY", "enochmgmt.com enzork@gmail.com"))


def _default_company_factory(symbol):
    return Company(symbol)


def get_insider_data(symbol, company_factory=None):
    """Look up recent Form 4 insider trading activity for a stock symbol via SEC EDGAR.

    Returns {"results": [...]} on success, or {"error": <message>}.
    """
    if not symbol or not symbol.strip():
        return {"error": NO_SYMBOL_ENTERED}

    symbol = symbol.strip().upper()

    try:
        factory = company_factory or _default_company_factory
        company = factory(symbol)
        filings = company.get_filings(form=FORM_TYPE)
    except (EdgarError, httpx.HTTPError, ValueError):
        return {"error": NO_INSIDER_DATA_FOUND}

    results = []
    for filing in filings[:MAX_FILINGS]:
        form4 = filing.obj()
        if not form4:
            continue
        summary = form4.get_ownership_summary()
        results.append(
            {
                "insider_name": summary.insider_name,
                "net_change": summary.net_change,
                "issuer": summary.issuer,
                "filing_date": str(filing.filing_date),
            }
        )

    return {"results": results}
