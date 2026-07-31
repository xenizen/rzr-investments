import os

from alpaca.common.exceptions import APIError
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

NO_STOCK_ENTERED = "No Stock Entered"
NO_PRICE_FOUND = "No Price Found: Real Stock?"


def _default_client():
    return StockHistoricalDataClient(
        os.environ.get("ALPACA_API_KEY"),
        os.environ.get("ALPACA_SECRET_KEY"),
    )


def get_stock_price(symbol, client=None):
    """Look up the latest trade price for a stock symbol via Alpaca.

    Returns {"price": float} on success, or {"error": <message>} using the
    exact error strings the task spec calls for.
    """
    if not symbol or not symbol.strip():
        return {"error": NO_STOCK_ENTERED}

    symbol = symbol.strip().upper()

    try:
        client = client or _default_client()
        trades = client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
    except (APIError, ValueError):
        # Covers both a lookup failure (bad/unknown symbol) and a client
        # that couldn't be constructed (e.g. missing Alpaca credentials) --
        # either way, no price is available.
        return {"error": NO_PRICE_FOUND}

    trade = trades.get(symbol) if trades else None
    if trade is None or trade.price is None:
        return {"error": NO_PRICE_FOUND}

    return {"price": trade.price}
