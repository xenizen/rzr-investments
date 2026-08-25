import app as app_module


def test_serve_frontend_returns_index_html_for_unknown_paths(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>investapp</html>")
    monkeypatch.setattr(app_module, "STATIC_DIR", str(tmp_path))
    client = app_module.app.test_client()

    response = client.get("/some/client/side/route")

    assert response.status_code == 200
    assert b"investapp" in response.data


def test_serve_frontend_returns_real_static_file_when_present(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>investapp</html>")
    (tmp_path / "app.js").write_text("console.log('hi')")
    monkeypatch.setattr(app_module, "STATIC_DIR", str(tmp_path))
    client = app_module.app.test_client()

    response = client.get("/app.js")

    assert response.status_code == 200
    assert b"console.log" in response.data


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


def test_insider_data_route_returns_result_from_get_insider_data(monkeypatch):
    monkeypatch.setattr(app_module, "get_insider_data", lambda symbol: {"results": []})
    client = app_module.app.test_client()

    response = client.get("/api/insider-data?symbol=AAPL")

    assert response.status_code == 200
    assert response.get_json() == {"results": []}


def test_insider_data_route_passes_blank_symbol_through(monkeypatch):
    captured = {}

    def fake_get_insider_data(symbol):
        captured["symbol"] = symbol
        return {"error": "No Stock Entered"}

    monkeypatch.setattr(app_module, "get_insider_data", fake_get_insider_data)
    client = app_module.app.test_client()

    response = client.get("/api/insider-data")

    assert response.get_json() == {"error": "No Stock Entered"}
    assert captured["symbol"] == ""
