#!/usr/bin/env bash
# Staleness check for the nightly Form 4 ingest (SCRUM-49). Schedule a few
# hours after the nightly job, e.g. cPanel Cron:
#
#   0 9 * * *  $HOME/<app-root>/scripts/check_ingest_fresh.sh
#
# Silent (exit 0) while the last successful run is recent. If there has been
# no success within MAX_AGE_HOURS it prints one line to stdout (which cron
# emails) and exits 1.
#
# Env:
#   INGEST_STATE_DIR  marker dir      (default: ~/.local/state/rzr-invest)
#   MAX_AGE_HOURS     staleness limit (default: 48)
set -uo pipefail

STATE_DIR="${INGEST_STATE_DIR:-$HOME/.local/state/rzr-invest}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-48}"
marker="$STATE_DIR/nightly-ok"

if [[ ! -f "$marker" ]]; then
    echo "rzr-invest Form 4 ingest: no successful run recorded yet ($marker missing)."
    exit 1
fi

last="$(cat "$marker" 2>/dev/null || true)"
if [[ ! "$last" =~ ^[0-9]+$ ]]; then
    echo "rzr-invest Form 4 ingest: marker $marker is unreadable or corrupt (got '$last')."
    exit 1
fi

age_hours=$(( ( $(date +%s) - last ) / 3600 ))
if (( age_hours > MAX_AGE_HOURS )); then
    echo "rzr-invest Form 4 ingest is STALE: last success ${age_hours}h ago (limit ${MAX_AGE_HOURS}h). Check $HOME/logs/form4-nightly.log."
    exit 1
fi
