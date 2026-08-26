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
