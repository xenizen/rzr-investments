"""Turn screener-pipeline failures into user-facing responses (SCRUM-36).

The endpoint (SCRUM-35) runs the screen inside try/except and calls
``classify`` on anything that escapes ``run_screen``. It distinguishes:

* ``ScreenerParamError`` -- an out-of-range query parameter. 400, and the
  message (which names the allowed values) goes straight to the client. The
  UI dropdowns mean users rarely trip this; it's for API robustness.
* an upstream being unavailable -- the Postgres store, Alpaca market data,
  or (only on the ``SCREENER_USE_DB=0`` fallback) SEC EDGAR. 5xx with a
  short "try again" line; the underlying error is logged, never shown.
* anything else -- 500, generic message, logged with a stack trace.

A screen that ran fine and simply matched nothing is *not* handled here --
``run_screen`` returns ``{"results": [], ...}`` and the endpoint sends that
through unchanged, so the UI can tell "no matches" from "it broke".
"""

from collections import namedtuple

import httpx
import psycopg

import alpaca_client
import db

try:  # Alpaca is a hard dependency, but keep classify() import-safe.
    from alpaca.common.exceptions import APIError
except ImportError:  # pragma: no cover
    APIError = ()


class ScreenerParamError(ValueError):
    """An out-of-range screener parameter.

    Subclasses ``ValueError`` so existing ``pytest.raises(ValueError)``
    checks and any generic callers keep working, while letting the endpoint
    tell a bad request apart from an unexpected ``ValueError`` deeper in the
    pipeline (which classifies as a 500).
    """


# log: "skip" (client error, nothing to record), "warning" (expected
# upstream blip -- one line, no trace), "exception" (unexpected or a
# misconfiguration ops needs to see -- full stack trace).
Classification = namedtuple("Classification", "message status log")

_STORE_DOWN = "The screener is temporarily unavailable. Please try again in a moment."
_PRICE_DOWN = "Market price data is temporarily unavailable. Please try again in a moment."
_PRICE_RATE_LIMITED = "Market price data is rate-limited right now. Please try again in a minute."
_UNEXPECTED = "Something went wrong running the screen. Please try again."


def _is_edgar_error(exc):
    """True for an edgartools exception, matched by module name so this
    module never imports edgartools (heavy: pandas/numpy) on the DB path."""
    return type(exc).__module__.split(".", 1)[0] == "edgar"


def classify(exc):
    """Map an exception from ``run_screen`` to a ``Classification``."""
    if isinstance(exc, ScreenerParamError):
        return Classification(str(exc), 400, "skip")

    if isinstance(exc, db.DatabaseNotConfigured):
        # A deployment that never set DATABASE_URL -- ops needs to see it.
        return Classification(_STORE_DOWN, 503, "exception")
    if isinstance(exc, psycopg.Error):
        return Classification(_STORE_DOWN, 503, "warning")

    if isinstance(exc, alpaca_client.AlpacaConfigError):
        return Classification(_PRICE_DOWN, 503, "exception")
    if APIError and isinstance(exc, APIError):
        if getattr(exc, "status_code", None) == 429:
            return Classification(_PRICE_RATE_LIMITED, 503, "warning")
        return Classification(_PRICE_DOWN, 502, "warning")

    if _is_edgar_error(exc) or isinstance(exc, httpx.HTTPError):
        return Classification(_STORE_DOWN, 503, "warning")

    return Classification(_UNEXPECTED, 500, "exception")
