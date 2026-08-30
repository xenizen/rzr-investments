"""CLI: load one or more quarterly form345 sources into ``form4_transactions``.

    python -m form4_ingest.backfill [--dry-run] PATH [PATH ...]

Each PATH is an extracted form345 directory or a ``*_form345.zip``. Safe to
re-run -- rows upsert on ``(accession_no, trans_sk)``. Run from ``backend/``
with ``DATABASE_URL`` set (or in ``backend/.env``).

Current backfill target (SCRUM-42): Q1 + Q2 2026, staged under
``backend/data/form345/``.
"""

import argparse
import sys

import env_setup  # noqa: F401 -- load backend/.env before db reads DATABASE_URL

from db import connection
from form4_ingest.bulk import BulkSourceError, parse_source
from form4_ingest.store import upsert_transactions


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="form4_ingest.backfill",
        description="Load quarterly form345 bulk data into form4_transactions.",
    )
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="a form345 directory or *_form345.zip")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and count only; write nothing")
    args = parser.parse_args(argv)

    total = 0
    try:
        if args.dry_run:
            for path in args.paths:
                count = sum(1 for _ in parse_source(path))
                print(f"{path}: {count} P/S Form 4 transactions (dry run)")
                total += count
        else:
            with connection() as conn:
                for path in args.paths:
                    count = upsert_transactions(conn, parse_source(path), source="bulk")
                    print(f"{path}: upserted {count} P/S Form 4 transactions")
                    total += count
    except BulkSourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
