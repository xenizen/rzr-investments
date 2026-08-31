"""Load ``backend/.env`` into the environment, if it exists.

``backend/.env`` (gitignored; see ``.env.example``) is how every
environment gets its config: ``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY`` /
``EDGAR_IDENTITY`` / ``DATABASE_URL`` for local dev and tests, and the same
file on the production host (the deploy runbook, ``docs/deploying.md``,
delivers it there). So ``.env`` is authoritative: ``override=True`` means a
value in the file wins over anything already in the environment -- e.g. a
stale key left behind in the host's app-server config.

Import this module *before* anything that reads ``os.environ`` at import
time (``insider_data`` and ``form4_ingest.edgar`` call ``set_identity`` on
import).
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)
