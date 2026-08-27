"""Shared Alpaca access for the Insider-Transaction Screener (epic SCRUM-29).

The screener is recommendations-only -- it never places orders. Alpaca is
used here for two read-only purposes:

* market data -- latest prices and daily bars (the 52-week-high filter,
  SCRUM-34), via ``StockHistoricalDataClient``;
* account context -- available funds and current positions shown for
  reference (SCRUM-35), via ``TradingClient``.

Credentials are app-level (one set for the whole app), read from the
environment -- there are no per-user Alpaca keys. The trading client is
pinned to Alpaca's paper environment: ``paper`` is not a parameter any
caller can change, so a misconfigured key cannot reach a live brokerage
account.
"""

import os

from alpaca.common.exceptions import APIError
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.trading.client import TradingClient

# Not configurable on purpose -- see the module docstring.
ALPACA_PAPER = True

MISSING_CREDENTIALS = (
    "Alpaca credentials are not configured. Set ALPACA_API_KEY and "
    "ALPACA_SECRET_KEY in the environment."
)


class AlpacaConfigError(RuntimeError):
    """Alpaca credentials are missing, so no client can be built.

    Distinct from alpaca's own ``APIError`` (a request that reached Alpaca
    and was rejected): this one never leaves the process. SCRUM-36 maps both
    to user-facing messages.
    """


def _credentials():
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise AlpacaConfigError(MISSING_CREDENTIALS)
    return api_key, secret_key


def market_data_client():
    """Build a read-only market-data client (latest prices, historical bars)."""
    api_key, secret_key = _credentials()
    return StockHistoricalDataClient(api_key, secret_key)


def trading_client():
    """Build a paper-only trading client, used solely to read account state.

    ``paper=ALPACA_PAPER`` is hard-wired; the screener has no live-trading
    path and pinning the environment keeps it that way.
    """
    api_key, secret_key = _credentials()
    return TradingClient(api_key, secret_key, paper=ALPACA_PAPER)


def get_latest_price(symbol, client=None):
    """Return the latest trade price for ``symbol``, or ``None`` if unavailable.

    Mirrors ``stock_price.get_stock_price``'s failure handling: a bad symbol
    or an unbuildable client both surface as ``None`` rather than raising.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None
    try:
        client = client or market_data_client()
        trades = client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
    except (AlpacaConfigError, APIError, ValueError):
        return None
    trade = trades.get(symbol) if trades else None
    if trade is None or trade.price is None:
        return None
    return trade.price


def get_account_context(client=None):
    """Return ``{"cash", "buying_power", "positions"}`` for the paper account.

    ``positions`` maps symbol -> signed quantity (float). Provided for the
    account-context display in SCRUM-35; the screener itself doesn't trade.
    """
    client = client or trading_client()
    account = client.get_account()
    positions = {p.symbol: float(p.qty) for p in client.get_all_positions()}
    return {
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "positions": positions,
    }
