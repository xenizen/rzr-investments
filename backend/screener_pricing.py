"""Price enrichment and the 52-week-high filter for the Insider-Transaction
Screener (SCRUM-29).

Takes the per-issuer candidates from ``screener.aggregate_by_issuer``, looks
up each ticker's current price and 52-week high from Alpaca, and keeps only
the ones trading far enough below their 52-week high.

The "percentage below 52-week high" parameter N is *how far below the high*
the price must be: a candidate is kept when

    current_price <= (1 - N/100) * fifty_two_week_high

so N=70 keeps stocks trading at 30% of their 52-week high or lower. N=100 is
degenerate (it would require price <= 0) and yields no matches.
"""

import logging

import alpaca_client

logger = logging.getLogger(__name__)

# The UI's "percentage below 52-week high" dropdown.
ALLOWED_PCT_BELOW_HIGH = (50, 60, 70, 80, 90, 100)


def _validate_pct_below_high(pct):
    try:
        value = int(pct)
    except (TypeError, ValueError):
        raise ValueError(f"pct_below_high must be one of {list(ALLOWED_PCT_BELOW_HIGH)}")
    if value not in ALLOWED_PCT_BELOW_HIGH:
        raise ValueError(f"pct_below_high must be one of {list(ALLOWED_PCT_BELOW_HIGH)}")
    return value


def enrich_and_filter(candidates, pct_below_high, *, price_lookup=None, high_lookup=None):
    """Price each candidate and drop the ones that don't clear the filter.

    Returns the kept candidates, each extended with ``current_price``,
    ``fifty_two_week_high``, ``price_ceiling`` (the (1 - N/100) x high cutoff)
    and ``discount_to_52w_high`` (1 - price/high).

    Tickers Alpaca can't price -- no current trade, or too little history for
    a 52-week high -- are dropped and logged. ``price_lookup`` / ``high_lookup``
    default to the batched ``alpaca_client`` helpers and are injectable for
    tests. Raises ``ValueError`` for a bad ``pct_below_high``.
    """
    pct = _validate_pct_below_high(pct_below_high)
    if not candidates:
        return []
    # N=100 -> ceiling of 0; nothing trades at or below $0.
    if pct >= 100:
        return []

    price_lookup = price_lookup or alpaca_client.get_latest_prices
    high_lookup = high_lookup or alpaca_client.get_52_week_highs

    tickers = [candidate["ticker"] for candidate in candidates]
    prices = price_lookup(tickers)
    highs = high_lookup(tickers)

    kept = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        price = prices.get(ticker)
        high = highs.get(ticker)

        if price is None:
            logger.info("screener: dropping %s -- no current price from Alpaca", ticker)
            continue
        if high is None or high <= 0:
            logger.info("screener: dropping %s -- insufficient history for a 52-week high", ticker)
            continue

        # high * (100 - pct) / 100, not high * (1 - pct/100) -- the latter
        # carries float error (1 - 0.8 = 0.199999...) that flips exact
        # boundary cases.
        ceiling = high * (100 - pct) / 100
        if price > ceiling:
            continue

        kept.append(
            {
                **candidate,
                "current_price": price,
                "fifty_two_week_high": high,
                "price_ceiling": ceiling,
                "discount_to_52w_high": 1 - price / high,
            }
        )
    return kept
