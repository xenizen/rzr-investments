from unittest.mock import MagicMock

import pytest
from alpaca.common.exceptions import APIError

import alpaca_client
from alpaca_client import (
    MIN_BARS_FOR_52W_HIGH,
    AlpacaConfigError,
    _clean_symbols,
    get_52_week_highs,
    get_account_context,
    get_latest_price,
    get_latest_prices,
    market_data_client,
    trading_client,
)


def _api_error(status_code):
    http_error = MagicMock()
    http_error.response.status_code = status_code
    return APIError('{"message":"invalid symbol: XXX"}', http_error)


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


def _bars(*highs):
    return [MagicMock(high=h) for h in highs]


def test_get_latest_prices_batches_and_maps_symbols():
    client = MagicMock()
    client.get_stock_latest_trade.return_value = {
        "AAPL": MagicMock(price=100.0),
        "MSFT": MagicMock(price=200.0),
    }

    result = get_latest_prices(["aapl", "msft"], client=client)

    assert result == {"AAPL": 100.0, "MSFT": 200.0}
    request = client.get_stock_latest_trade.call_args.args[0]
    assert request.symbol_or_symbols == ["AAPL", "MSFT"]


def test_get_latest_prices_omits_symbols_with_no_trade():
    client = MagicMock()
    client.get_stock_latest_trade.return_value = {"AAPL": MagicMock(price=100.0)}

    assert get_latest_prices(["AAPL", "ZZZZ"], client=client) == {"AAPL": 100.0}


def test_get_latest_prices_empty_input_makes_no_call():
    client = MagicMock()
    assert get_latest_prices([], client=client) == {}
    client.get_stock_latest_trade.assert_not_called()


def test_get_latest_prices_propagates_non_400_api_error():
    # 429 rate limit / 401 auth must surface, not be silently swallowed.
    client = MagicMock()
    client.get_stock_latest_trade.side_effect = _api_error(429)
    with pytest.raises(APIError):
        get_latest_prices(["AAPL"], client=client)


def test_get_latest_prices_falls_back_to_per_symbol_on_batch_400():
    # One bad symbol 400s the whole batch; retry symbol-by-symbol and keep
    # what resolves.
    client = MagicMock()

    def per_call(request):
        symbols = request.symbol_or_symbols
        if symbols == ["AAPL", "MSFT"]:
            raise _api_error(400)
        if symbols == ["AAPL"]:
            return {"AAPL": MagicMock(price=100.0)}
        raise _api_error(400)  # MSFT is the bad one

    client.get_stock_latest_trade.side_effect = per_call

    assert get_latest_prices(["AAPL", "MSFT"], client=client) == {"AAPL": 100.0}


def test_invalid_symbols_are_filtered_before_the_request():
    client = MagicMock()
    client.get_stock_latest_trade.return_value = {"AAPL": MagicMock(price=100.0)}

    get_latest_prices(["AAPL", "AXIA3", "BRK.A", "TOO.LONG.SYM", ""], client=client)

    assert client.get_stock_latest_trade.call_args.args[0].symbol_or_symbols == ["AAPL", "BRK.A"]


@pytest.mark.parametrize(
    "symbol, kept",
    [
        ("AAPL", True),
        ("aapl", True),
        ("BRK.A", True),
        ("AXIA3", False),
        ("SPY5", False),
        ("TOOLONG", False),
        ("A-B", False),
        ("", False),
    ],
)
def test_clean_symbols_filter(symbol, kept):
    assert (_clean_symbols([symbol]) == [symbol.strip().upper()]) is kept


def test_get_52_week_highs_returns_max_high_per_symbol():
    client = MagicMock()
    client.get_stock_bars.return_value = MagicMock(
        data={
            "AAPL": _bars(*([150.0] * (MIN_BARS_FOR_52W_HIGH - 1) + [242.0])),
            "MSFT": _bars(*([400.0] * MIN_BARS_FOR_52W_HIGH)),
        }
    )

    assert get_52_week_highs(["AAPL", "MSFT"], client=client) == {"AAPL": 242.0, "MSFT": 400.0}


def test_get_52_week_highs_skips_symbols_with_insufficient_history():
    client = MagicMock()
    client.get_stock_bars.return_value = MagicMock(
        data={
            "NEW": _bars(*([50.0] * (MIN_BARS_FOR_52W_HIGH - 1))),  # one short
            "OLD": _bars(*([50.0] * MIN_BARS_FOR_52W_HIGH)),
        }
    )

    assert get_52_week_highs(["NEW", "OLD"], client=client) == {"OLD": 50.0}


def test_get_52_week_highs_skips_symbols_with_no_bars():
    client = MagicMock()
    client.get_stock_bars.return_value = MagicMock(data={})

    assert get_52_week_highs(["AAPL"], client=client) == {}


def test_get_52_week_highs_propagates_non_400_api_error():
    client = MagicMock()
    client.get_stock_bars.side_effect = _api_error(429)
    with pytest.raises(APIError):
        get_52_week_highs(["AAPL"], client=client)


def test_get_52_week_highs_falls_back_to_per_symbol_on_batch_400():
    client = MagicMock()
    good = _bars(*([10.0] * (MIN_BARS_FOR_52W_HIGH - 1) + [99.0]))

    def per_call(request):
        symbols = request.symbol_or_symbols
        if symbols == ["AAPL", "MSFT"]:
            raise _api_error(400)
        if symbols == ["AAPL"]:
            return MagicMock(data={"AAPL": good})
        raise _api_error(400)

    client.get_stock_bars.side_effect = per_call

    assert get_52_week_highs(["AAPL", "MSFT"], client=client) == {"AAPL": 99.0}


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
