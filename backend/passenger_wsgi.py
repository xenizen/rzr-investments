import os
import sys

# Shared hosting caps the account's process/thread count (CloudLinux CageFS).
# OpenBLAS -- pulled in transitively by edgartools via numpy/pandas -- tries
# to spin up one thread per CPU core on import by default, which blows past
# that cap on a constrained host and can hang or crash app startup. Force it
# down to a single thread before anything numpy-related gets imported.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app as application
