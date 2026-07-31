import app as app_module


def test_stock_price_route_returns_result_from_get_stock_price(monkeypatch):
    monkeypatch.setattr(app_module, "get_stock_price", lambda symbol: {"price": 42.0})
    client = app_module.app.test_client()

    response = client.get("/api/stock-price?symbol=AAPL")

    assert response.status_code == 200
    assert response.get_json() == {"price": 42.0}


def test_stock_price_route_passes_blank_symbol_through(monkeypatch):
    captured = {}

    def fake_get_stock_price(symbol):
        captured["symbol"] = symbol
        return {"error": "No Stock Entered"}

    monkeypatch.setattr(app_module, "get_stock_price", fake_get_stock_price)
    client = app_module.app.test_client()

    response = client.get("/api/stock-price")

    assert response.get_json() == {"error": "No Stock Entered"}
    assert captured["symbol"] == ""
