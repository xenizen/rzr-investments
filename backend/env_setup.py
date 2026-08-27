"""Load ``backend/.env`` into the environment, if it exists.

Deployment sets real environment variables through the WSGI host, so this
is a no-op there. It's a convenience for local dev and tests, where a
gitignored ``backend/.env`` (see ``.env.example``) is easier than exporting
``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY`` / ``EDGAR_IDENTITY`` by hand.

Import this module *before* anything that reads ``os.environ`` at import
time (``insider_data`` and ``screener_data`` call ``set_identity`` on
import). Real environment variables always win -- ``load_dotenv`` does not
override values that are already set.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
