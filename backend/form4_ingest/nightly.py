"""CLI for the nightly incremental Form 4 ingest (SCRUM-45).

    python -m form4_ingest.nightly [--since YYYY-MM-DD] [--days N] [--dry-run]

Cron-friendly: logs to stderr, exits non-zero on any failure. With no
options it pulls from the newest stored ``filing_date`` through today;
``--since`` overrides the start (use it to bound the first catch-up run),
``--days`` sets the fallback window used only when the table is empty.
"""

import argparse
import logging
import sys
from datetime import date

import env_setup  # noqa: F401 -- load backend/.env before db / edgar read the env

from db import connection
from form4_ingest.edgar import DEFAULT_FALLBACK_DAYS, MAX_FILINGS_PER_RUN, ingest

log = logging.getLogger("form4_ingest.nightly")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="form4_ingest.nightly", description=__doc__)
    parser.add_argument(
        "--since", type=date.fromisoformat, metavar="YYYY-MM-DD",
        help="start date (default: newest stored filing_date)",
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_FALLBACK_DAYS, metavar="N",
        help=f"fallback window when the table is empty (default {DEFAULT_FALLBACK_DAYS})",
    )
    parser.add_argument(
        "--max-filings", type=int, default=MAX_FILINGS_PER_RUN, metavar="N",
        help=f"cap filings parsed per run; 0 lifts the cap (default {MAX_FILINGS_PER_RUN})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch and parse only; write nothing",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        with connection() as conn:
            summary = ingest(
                conn,
                since=args.since,
                fallback_days=args.days,
                max_filings=args.max_filings,
                dry_run=args.dry_run,
            )
    except Exception:
        log.exception("form4 ingest failed")
        return 1

    print(
        f"window {summary['window_start']}..{summary['window_end']}  "
        f"filings={summary['filings_parsed']}/{summary['filings_in_window']}  "
        f"parsed={summary['records_parsed']}  upserted={summary['rows_upserted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
