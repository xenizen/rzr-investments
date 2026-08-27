import os

# Same fix as passenger_wsgi.py, applied for this entry point too: OpenBLAS
# (pulled in transitively by edgartools via numpy/pandas) tries to spin up
# one thread per CPU core on import, which can exhaust a constrained host's
# process/thread limits. pytest imports insider_data (and therefore edgar)
# directly, never executing passenger_wsgi.py, so it needs the same guard.
# Set here, in conftest.py, so it's in place before any test module's
# imports run.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# Load backend/.env (if present) so integration-style checks can hit real
# Alpaca/EDGAR. Unit tests still stub their clients; test_alpaca_client.py
# clears ALPACA_* per-test regardless.
import env_setup  # noqa: E402,F401
