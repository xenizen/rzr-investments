"""Which Form 4 source the screener reads from (SCRUM-46).

``screener_repo`` (the ``form4_transactions`` DB) is the default. The old
live-EDGAR path (``screener_data``) stays reachable behind an env flag as a
fallback while the ingest jobs bed in. SCRUM-48 deletes this shim and
``screener_data`` once the DB is trusted; the screener endpoint (SCRUM-35)
should import from here, not from either source directly.

    SCREENER_USE_DB=0   # fall back to a live EDGAR pull (no months window)
"""

import os

import screener_repo

USE_DB_ENV = "SCREENER_USE_DB"


def _use_db():
    return os.environ.get(USE_DB_ENV, "1").strip().lower() not in ("0", "false", "no")


def get_insider_transactions(direction=screener_repo.DEFAULT_DIRECTION, *,
                             months=screener_repo.DEFAULT_MONTHS):
    """Normalized Form 4 records for ``direction`` over the trailing
    ``months`` window. Delegates to the DB, or to the legacy live-EDGAR
    path when ``SCREENER_USE_DB`` is off (that path ignores ``months`` --
    it only ever sees the most recent ~day of filings)."""
    if _use_db():
        return screener_repo.get_insider_transactions(direction, months=months)

    import screener_data  # imported lazily: pulls in edgar/pandas

    return screener_data.get_insider_transactions(direction)
