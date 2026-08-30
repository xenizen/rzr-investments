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
    monkeypatch.setattr(app_module, "get_insider_data", lambda **kwargs: {"results": []})
    client = app_module.app.test_client()

    response = client.get("/api/insider-data?symbol=AAPL")

    assert response.status_code == 200
    assert response.get_json() == {"results": []}


def test_insider_data_route_passes_all_filter_params_through(monkeypatch):
    captured = {}

    def fake_get_insider_data(**kwargs):
        captured.update(kwargs)
        return {"results": []}

    monkeypatch.setattr(app_module, "get_insider_data", fake_get_insider_data)
    client = app_module.app.test_client()

    client.get("/api/insider-data?symbol=AAPL&name=Jane&date_from=2026-01-01&date_to=2026-02-01&page=2")

    assert captured == {
        "symbol": "AAPL",
        "name": "Jane",
        "date_from": "2026-01-01",
        "date_to": "2026-02-01",
        "page": "2",
    }


def test_insider_data_route_passes_blank_params_through(monkeypatch):
    captured = {}

    def fake_get_insider_data(**kwargs):
        captured.update(kwargs)
        return {"error": "No Stock Entered"}

    monkeypatch.setattr(app_module, "get_insider_data", fake_get_insider_data)
    client = app_module.app.test_client()

    response = client.get("/api/insider-data")

    assert response.get_json() == {"error": "No Stock Entered"}
    assert captured == {"symbol": "", "name": "", "date_from": "", "date_to": "", "page": 1}


def test_insider_screener_route_returns_run_screen_result(monkeypatch):
    monkeypatch.setattr(
        app_module, "run_screen", lambda **kwargs: {"results": [], "total_count": 0}
    )
    client = app_module.app.test_client()

    response = client.get("/api/insider-screener")

    assert response.status_code == 200
    assert response.get_json() == {"results": [], "total_count": 0}
    assert response.headers["Cache-Control"] == "no-store"


def test_insider_screener_route_passes_params_through(monkeypatch):
    captured = {}

    def fake_run_screen(**kwargs):
        captured.update(kwargs)
        return {"results": []}

    monkeypatch.setattr(app_module, "run_screen", fake_run_screen)
    client = app_module.app.test_client()

    client.get("/api/insider-screener?direction=Sold&shares=15000&pct_below_high=80&months=3&page=2")

    assert captured == {
        "direction": "Sold",
        "min_shares": "15000",
        "pct_below_high": "80",
        "months": "3",
        "page": "2",
    }


def test_insider_screener_route_defaults(monkeypatch):
    captured = {}
    monkeypatch.setattr(app_module, "run_screen", lambda **kw: captured.update(kw) or {"results": []})
    client = app_module.app.test_client()

    client.get("/api/insider-screener")

    assert captured == {
        "direction": "Purchase",
        "min_shares": 10000,
        "pct_below_high": 70,
        "months": 1,
        "page": 1,
    }


def test_insider_screener_route_maps_param_error_to_400(monkeypatch):
    from screener_errors import ScreenerParamError

    def boom(**kwargs):
        raise ScreenerParamError("months must be one of [1, 2, 3, 4, 5, 6]")

    monkeypatch.setattr(app_module, "run_screen", boom)
    client = app_module.app.test_client()

    response = client.get("/api/insider-screener?months=9")

    assert response.status_code == 400
    assert response.get_json() == {"error": "months must be one of [1, 2, 3, 4, 5, 6]"}


def test_insider_screener_route_maps_upstream_failure_to_friendly_5xx(monkeypatch):
    import psycopg

    def boom(**kwargs):
        raise psycopg.OperationalError("FATAL: connection refused at 10.0.0.5:5432")

    monkeypatch.setattr(app_module, "run_screen", boom)
    client = app_module.app.test_client()

    response = client.get("/api/insider-screener")
    body = response.get_json()

    assert response.status_code == 503
    assert body["error"] == "The screener is temporarily unavailable. Please try again in a moment."
    assert "connection refused" not in body["error"]  # no leak
    assert "10.0.0.5" not in body["error"]


def test_insider_screener_route_maps_unexpected_error_to_generic_500(monkeypatch):
    def boom(**kwargs):
        raise KeyError("fifty_two_week_high")

    monkeypatch.setattr(app_module, "run_screen", boom)
    client = app_module.app.test_client()

    response = client.get("/api/insider-screener")

    assert response.status_code == 500
    assert response.get_json() == {
        "error": "Something went wrong running the screen. Please try again."
    }


def test_insider_screener_route_real_bad_param_returns_400(monkeypatch):
    # No monkeypatch of run_screen -- exercises _validated() -> the endpoint.
    # months validation happens before any DB call, so this needs no DB.
    client = app_module.app.test_client()

    response = client.get("/api/insider-screener?months=99")

    assert response.status_code == 400
    assert "months" in response.get_json()["error"]
