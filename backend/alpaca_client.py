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
from datetime import datetime, timedelta, timezone

from alpaca.common.exceptions import APIError
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient

# Not configurable on purpose -- see the module docstring.
ALPACA_PAPER = True

# 52-week-high inputs. We ask for a little over 52 weeks of daily bars (the
# few extra days at the far end don't matter for a "high") and require a
# minimum bar count before trusting the result -- a stock that only listed a
# few months ago has no meaningful 52-week high, and showing a deep
# "discount" off a 2-month high would be misleading.
BARS_LOOKBACK = timedelta(weeks=53)
MIN_BARS_FOR_52W_HIGH = 200

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


def get_latest_prices(symbols, client=None):
    """Latest trade price for each of ``symbols`` -- a batched ``get_latest_price``.

    Returns ``{symbol: price}``, omitting any symbol Alpaca had no priceable
    trade for. Unlike the single-symbol helper this does not swallow API
    errors: a failed batch call (rate limit, auth) propagates so the caller
    can surface it (SCRUM-36).
    """
    symbols = _clean_symbols(symbols)
    if not symbols:
        return {}
    client = client or market_data_client()
    trades = client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbols))
    prices = {}
    for symbol in symbols:
        trade = trades.get(symbol) if trades else None
        if trade is not None and trade.price is not None:
            prices[symbol] = trade.price
    return prices


def get_52_week_highs(symbols, client=None):
    """52-week high for each of ``symbols``, from ~1 year of daily bars.

    Returns ``{symbol: high}``, omitting any symbol with no bars or fewer
    than ``MIN_BARS_FOR_52W_HIGH`` (treated as insufficient history). A
    failed batch call propagates (see ``get_latest_prices``).
    """
    symbols = _clean_symbols(symbols)
    if not symbols:
        return {}
    client = client or market_data_client()
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=datetime.now(timezone.utc) - BARS_LOOKBACK,
    )
    bars = client.get_stock_bars(request)
    data = getattr(bars, "data", None) or {}

    highs = {}
    for symbol in symbols:
        symbol_bars = data.get(symbol) or []
        if len(symbol_bars) < MIN_BARS_FOR_52W_HIGH:
            continue
        valid = [bar.high for bar in symbol_bars if bar.high is not None]
        if valid:
            highs[symbol] = max(valid)
    return highs


def _clean_symbols(symbols):
    seen = []
    for symbol in symbols or []:
        symbol = (symbol or "").strip().upper()
        if symbol and symbol not in seen:
            seen.append(symbol)
    return seen


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
