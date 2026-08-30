"""Parallel SEC-filing loading with a shared-hosting fallback.

Fetching and parsing individual EDGAR filings via edgartools is IO-bound, so
a thread pool speeds up a batch. But some shared hosts (CloudLinux CageFS
accounts) cap the process/thread count so tightly that the pool can't even
start -- a plain ``RuntimeError``, not one of edgartools' error types. In
that case fall back to loading sequentially rather than fail the whole
batch.

Used by ``insider_data`` (the Insider Data endpoint) and
``form4_ingest.edgar`` (the nightly Form 4 ingest).
"""

from concurrent.futures import ThreadPoolExecutor

# A pool this size keeps a page / day's worth of fetches in flight at once
# without unbounded thread growth. Callers can override.
DEFAULT_MAX_WORKERS = 10


def load_filings(items, loader, *, max_workers=DEFAULT_MAX_WORKERS):
    """Map ``loader`` over ``items`` in parallel, results in input order.

    Falls back to sequential mapping if the thread pool can't be started.
    ``loader`` is expected to swallow its own per-item errors (returning a
    sentinel / empty result), so this never partially fails a batch.
    """
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        return list(executor.map(loader, items))
    except RuntimeError:
        return [loader(item) for item in items]
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
