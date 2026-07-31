from unittest.mock import MagicMock

from alpaca.common.exceptions import APIError

from stock_price import NO_PRICE_FOUND, NO_STOCK_ENTERED, get_stock_price


def _client_returning(trades):
    client = MagicMock()
    client.get_stock_latest_trade.return_value = trades
    return client


def test_blank_symbol_returns_no_stock_entered():
    assert get_stock_price("") == {"error": NO_STOCK_ENTERED}
    assert get_stock_price("   ") == {"error": NO_STOCK_ENTERED}
    assert get_stock_price(None) == {"error": NO_STOCK_ENTERED}


def test_known_symbol_returns_price():
    trade = MagicMock(price=123.45)
    client = _client_returning({"AAPL": trade})

    result = get_stock_price("aapl", client=client)

    assert result == {"price": 123.45}


def test_unknown_symbol_returns_no_price_found():
    client = _client_returning({})

    result = get_stock_price("ZZZZZ", client=client)

    assert result == {"error": NO_PRICE_FOUND}


def test_alpaca_api_error_returns_no_price_found():
    client = MagicMock()
    client.get_stock_latest_trade.side_effect = APIError("bad symbol")

    result = get_stock_price("BADSYM", client=client)

    assert result == {"error": NO_PRICE_FOUND}


def test_missing_credentials_returns_no_price_found(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    result = get_stock_price("AAPL")  # no client override -> hits _default_client()

    assert result == {"error": NO_PRICE_FOUND}
