"""The screener pipeline, end to end (SCRUM-35).

``run_screen`` is the one call the API endpoint makes. It chains the pieces
built by the earlier stories:

    screener_source.get_insider_transactions   (SCRUM-46 -> DB, or SCRUM-32)
        -> screener.aggregate_by_issuer        (SCRUM-33: threshold + rollup)
        -> screener_pricing.enrich_and_filter  (SCRUM-34: price + 52wk filter)
        -> rank
        -> paginate

then shapes each survivor into a result row the frontend renders and that
can later be handed to Stock Purchase (SCRUM-3): ticker + side + a suggested
quantity.

Recommendations only -- nothing here places an order.
"""

import math

import screener
import screener_pricing
import screener_repo
import screener_source

PAGE_SIZE = 10

# What we suggest buying/selling if the user acts on a row. The screen's own
# "insider transaction size" threshold is the natural unit -- it's the size
# of the insider activity that made this a candidate. Confirmed as the
# SCRUM-3 hand-off quantity during the SCRUM-35 build.
def _suggested_quantity(min_shares):
    return int(min_shares)


def _parse_page(page):
    try:
        page = int(page)
    except (TypeError, ValueError):
        return 1
    return page if page >= 1 else 1


def _rank(candidates):
    """Deterministic ranking: multi-insider first, then aggregate insider
    share volume, then discount to the 52-week high -- all descending. Ties
    break on ticker ascending so a fixed input always ranks the same way."""
    ranked = sorted(candidates, key=lambda c: c["ticker"])
    ranked.sort(
        key=lambda c: (c["multiple_insiders"], c["total_shares"], c["discount_to_52w_high"]),
        reverse=True,
    )
    return ranked


def _row(candidate, min_shares):
    return {
        "ticker": candidate["ticker"],
        "company": candidate["issuer_name"],
        "side": "buy" if candidate["transaction_code"] == "P" else "sell",
        "insider_count": candidate["insider_count"],
        "multiple_insiders": candidate["multiple_insiders"],
        "insiders": candidate["insiders"],
        "total_insider_shares": candidate["total_shares"],
        "current_price": candidate["current_price"],
        "fifty_two_week_high": candidate["fifty_two_week_high"],
        "discount_pct": round(candidate["discount_to_52w_high"] * 100, 1),
        "suggested_quantity": _suggested_quantity(min_shares),
        "filings": [
            {
                "accession_no": txn["accession_no"],
                "filing_date": txn["filing_date"],
                "transaction_date": txn["transaction_date"],
                "insider_name": txn["insider_name"],
                "shares": txn["shares"],
                "price": txn["price"],
            }
            for txn in candidate["transactions"]
        ],
    }


def run_screen(
    direction=screener_repo.DEFAULT_DIRECTION,
    min_shares=10000,
    pct_below_high=70,
    *,
    months=screener_repo.DEFAULT_MONTHS,
    page=1,
    transactions_source=None,
    price_lookup=None,
    high_lookup=None,
):
    """Run one screen and return a page of ranked results.

    Parameters map to the UI dropdowns: ``direction`` ("Purchase"/"Sold"),
    ``min_shares`` (5000/10000/15000/20000), ``pct_below_high``
    (50..100), plus ``months`` (1-6 lookback) and ``page``.

    Returns::

        {results: [row, ...], page, page_size, total_count, total_pages,
         has_next}

    Raises ``ValueError`` for any out-of-range parameter (the source's
    ``direction``/``months``, the aggregator's ``min_shares``, the pricer's
    ``pct_below_high``) -- SCRUM-36 maps those to user-facing messages.
    ``*_source`` / ``*_lookup`` are injectable for tests.
    """
    source = transactions_source or screener_source.get_insider_transactions
    page = _parse_page(page)

    transactions = source(direction, months=months)
    candidates = screener.aggregate_by_issuer(transactions, min_shares)
    priced = screener_pricing.enrich_and_filter(
        candidates, pct_below_high, price_lookup=price_lookup, high_lookup=high_lookup
    )
    ranked = _rank(priced)

    total_count = len(ranked)
    total_pages = max(1, math.ceil(total_count / PAGE_SIZE))
    start = (page - 1) * PAGE_SIZE
    window = ranked[start : start + PAGE_SIZE]

    return {
        "results": [_row(candidate, min_shares) for candidate in window],
        "page": page,
        "page_size": PAGE_SIZE,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_next": start + PAGE_SIZE < total_count,
    }
