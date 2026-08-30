from unittest.mock import MagicMock

import httpx
import psycopg
import pytest
from alpaca.common.exceptions import APIError

import alpaca_client
import db
from screener_errors import ScreenerParamError, classify


def _api_error(status_code):
    http_error = MagicMock()
    http_error.response.status_code = status_code
    return APIError('{"message":"nope"}', http_error)


def test_param_error_is_a_400_passed_through_verbatim():
    result = classify(ScreenerParamError("months must be one of [1, 2, 3, 4, 5, 6]"))
    assert result.status == 400
    assert result.message == "months must be one of [1, 2, 3, 4, 5, 6]"
    assert result.log == "skip"


def test_database_not_configured_is_a_logged_503():
    result = classify(db.DatabaseNotConfigured("DATABASE_URL is not set"))
    assert result.status == 503
    assert "temporarily unavailable" in result.message
    assert result.log == "exception"  # ops needs to see a misconfig


def test_psycopg_error_is_a_quiet_503():
    result = classify(psycopg.OperationalError("connection refused"))
    assert result.status == 503
    assert result.log == "warning"
    assert "connection refused" not in result.message  # no leak


def test_alpaca_missing_credentials_is_a_logged_503():
    result = classify(alpaca_client.AlpacaConfigError("no creds"))
    assert result.status == 503
    assert "price data" in result.message.lower()
    assert result.log == "exception"


def test_alpaca_rate_limit_is_a_503_with_its_own_message():
    result = classify(_api_error(429))
    assert result.status == 503
    assert "rate-limited" in result.message
    assert result.log == "warning"


def test_other_alpaca_api_error_is_a_502():
    result = classify(_api_error(500))
    assert result.status == 502
    assert "price data" in result.message.lower()


def test_edgar_error_classified_by_module_name_without_importing_edgar():
    fake_edgar_exc = type("EdgarError", (Exception,), {"__module__": "edgar.exceptions"})()
    result = classify(fake_edgar_exc)
    assert result.status == 503
    assert result.log == "warning"


def test_httpx_error_is_a_503():
    result = classify(httpx.ConnectError("dns failure"))
    assert result.status == 503


def test_unexpected_exception_is_a_generic_logged_500():
    result = classify(KeyError("issuer_ticker"))
    assert result.status == 500
    assert result.message == "Something went wrong running the screen. Please try again."
    assert result.log == "exception"
    assert "issuer_ticker" not in result.message


def test_bare_value_error_is_not_treated_as_a_param_error():
    # Only ScreenerParamError -> 400. A ValueError from deeper in the
    # pipeline is unexpected -> 500.
    result = classify(ValueError("could not convert string to float"))
    assert result.status == 500


def test_screener_param_error_is_a_value_error():
    assert issubclass(ScreenerParamError, ValueError)
