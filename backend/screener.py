"""Screening and aggregation for the Insider-Transaction Screener (SCRUM-29).

Takes the normalized Form 4 transaction records from ``screener_data`` and
rolls them up into per-issuer candidates: apply the share-size signal
threshold, group what's left by issuer ticker, and flag issuers where more
than one distinct insider transacted the same way.

Downstream, SCRUM-34 prices each candidate and applies the 52-week-high
filter, and SCRUM-35 ranks and paginates them.
"""

# The UI's "number of shares" dropdown. The threshold is a signal filter on
# each insider transaction's size -- not a purchase quantity (see SCRUM-29).
ALLOWED_SHARE_SIZES = (5000, 10000, 15000, 20000)


def _validate_min_shares(min_shares):
    try:
        value = int(min_shares)
    except (TypeError, ValueError):
        raise ValueError(f"min_shares must be one of {list(ALLOWED_SHARE_SIZES)}")
    if value not in ALLOWED_SHARE_SIZES:
        raise ValueError(f"min_shares must be one of {list(ALLOWED_SHARE_SIZES)}")
    return value


def _insider_key(record):
    """Dedup key for counting distinct insiders -- CIK first (SCRUM-33 AC),
    falling back to the lowercased name only when a filing carried no CIK, so
    one insider isn't double-counted and two aren't merged."""
    cik = (record.get("insider_cik") or "").strip()
    if cik:
        return f"cik:{cik}"
    return f"name:{(record.get('insider_name') or '').strip().lower()}"


def aggregate_by_issuer(transactions, min_shares):
    """Roll transaction records up into per-issuer screening candidates.

    Only transactions of at least ``min_shares`` shares count toward a
    candidate. Returns a list of candidate dicts, one per issuer ticker with
    at least one qualifying transaction, ordered by ticker:

        {ticker, issuer_cik, issuer_name, transaction_code,
         total_shares, insider_count, multiple_insiders,
         insiders: [name, ...], transactions: [record, ...]}

    ``insider_count`` is the number of distinct insiders (by CIK, falling
    back to name when a filing has no CIK). ``multiple_insiders`` is
    ``insider_count >= 2``. All records in a group already share an issuer
    and a transaction direction (``screener_data`` filters to one code), so
    the "same direction, same issuer" part of the flag is implicit.

    Raises ``ValueError`` for a ``min_shares`` outside ALLOWED_SHARE_SIZES.
    """
    min_shares = _validate_min_shares(min_shares)

    groups = {}
    for record in transactions:
        shares = record.get("shares")
        if shares is None or shares < min_shares:
            continue
        ticker = (record.get("issuer_ticker") or "").upper()
        if not ticker:
            continue
        groups.setdefault(ticker, []).append(record)

    candidates = []
    for ticker, records in sorted(groups.items()):
        distinct_insiders = {_insider_key(r) for r in records}
        insider_names = sorted(
            {name for r in records if (name := (r.get("insider_name") or "").strip())}
        )
        ordered = sorted(
            records, key=lambda r: (r["transaction_date"], r["accession_no"]), reverse=True
        )

        candidates.append(
            {
                "ticker": ticker,
                "issuer_cik": records[0].get("issuer_cik", ""),
                "issuer_name": records[0].get("issuer_name", ""),
                "transaction_code": records[0].get("transaction_code", ""),
                "total_shares": sum(r["shares"] for r in records),
                "insider_count": len(distinct_insiders),
                "multiple_insiders": len(distinct_insiders) >= 2,
                "insiders": insider_names,
                "transactions": ordered,
            }
        )
    return candidates
