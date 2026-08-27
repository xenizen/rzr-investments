from unittest.mock import MagicMock

import pytest
from alpaca.common.exceptions import APIError

import alpaca_client
from alpaca_client import (
    AlpacaConfigError,
    get_account_context,
    get_latest_price,
    market_data_client,
    trading_client,
)


@pytest.fixture(autouse=True)
def _clear_credentials(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)


def _set_credentials(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")


def _client_returning_trade(price):
    client = MagicMock()
    client.get_stock_latest_trade.return_value = {"AAPL": MagicMock(price=price)}
    return client


def test_client_factories_raise_without_credentials():
    with pytest.raises(AlpacaConfigError):
        market_data_client()
    with pytest.raises(AlpacaConfigError):
        trading_client()


def test_trading_client_is_pinned_to_paper(monkeypatch):
    _set_credentials(monkeypatch)
    captured = {}

    def fake_trading_client(api_key, secret_key, paper):
        captured.update(api_key=api_key, secret_key=secret_key, paper=paper)
        return MagicMock()

    monkeypatch.setattr(alpaca_client, "TradingClient", fake_trading_client)

    trading_client()

    assert captured == {"api_key": "test-key", "secret_key": "test-secret", "paper": True}


def test_get_latest_price_returns_price_with_injected_client():
    assert get_latest_price("aapl", client=_client_returning_trade(123.45)) == 123.45


def test_get_latest_price_returns_none_for_blank_symbol():
    assert get_latest_price("", client=_client_returning_trade(1.0)) is None


def test_get_latest_price_returns_none_for_unknown_symbol():
    client = MagicMock()
    client.get_stock_latest_trade.return_value = {}
    assert get_latest_price("ZZZZZ", client=client) is None


def test_get_latest_price_returns_none_on_api_error():
    client = MagicMock()
    client.get_stock_latest_trade.side_effect = APIError("bad symbol")
    assert get_latest_price("BADSYM", client=client) is None


def test_get_latest_price_returns_none_without_credentials():
    # No injected client -> falls through to market_data_client(), which
    # raises AlpacaConfigError; get_latest_price swallows it.
    assert get_latest_price("AAPL") is None


def test_get_account_context_maps_account_and_positions():
    client = MagicMock()
    client.get_account.return_value = MagicMock(cash="1000.50", buying_power="2500.00")
    client.get_all_positions.return_value = [
        MagicMock(symbol="AAPL", qty="10"),
        MagicMock(symbol="MSFT", qty="-3"),
    ]

    assert get_account_context(client=client) == {
        "cash": 1000.50,
        "buying_power": 2500.00,
        "positions": {"AAPL": 10.0, "MSFT": -3.0},
    }
