#!/usr/bin/env bash
# Nightly Form 4 ingest wrapper (SCRUM-49). Schedule from cPanel Cron:
#
#   PYTHON=$HOME/virtualenv/<app-root>/<pyver>/bin/python
#   30 5 * * *  $HOME/<app-root>/scripts/nightly_ingest.sh
#
# Runs `python -m form4_ingest.nightly`, appends everything to a log, and
# records the last successful run. Silent on success so cron sends no mail;
# on failure it prints the tail of the log to stdout (which cron emails)
# and exits non-zero.
#
# Env:
#   PYTHON            python to use (default: python3 on PATH)
#   INGEST_LOG        log file      (default: ~/logs/form4-nightly.log)
#   INGEST_STATE_DIR  marker dir    (default: ~/.local/state/rzr-invest)
# Extra args pass through to form4_ingest.nightly (e.g. --max-filings 0).
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYBIN="${PYTHON:-python3}"
LOG="${INGEST_LOG:-$HOME/logs/form4-nightly.log}"
STATE_DIR="${INGEST_STATE_DIR:-$HOME/.local/state/rzr-invest}"

mkdir -p "$(dirname "$LOG")" "$STATE_DIR"
cd "$here"

echo "=== $(date +%FT%T) nightly ingest starting ===" >> "$LOG"
if "$PYBIN" -m form4_ingest.nightly "$@" >> "$LOG" 2>&1; then
    date +%s > "$STATE_DIR/nightly-ok"
    echo "=== $(date +%FT%T) nightly ingest ok ===" >> "$LOG"
    exit 0
else
    status=$?
    echo "=== $(date +%FT%T) nightly ingest FAILED (exit $status) ===" >> "$LOG"
    echo "rzr-invest Form 4 nightly ingest FAILED (exit $status). Last lines of $LOG:"
    tail -n 25 "$LOG"
    exit "$status"
fi
