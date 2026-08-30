#!/usr/bin/env bash
# Daily pg_dump of the Form 4 store (SCRUM-50). Schedule from cPanel Cron:
#
#   15 4 * * *  cd ~/<app-root>/backend && ./scripts/backup_db.sh >> ~/logs/db-backup.log 2>&1
#
# Reads DATABASE_URL from backend/.env (same as the app). Writes a
# gzip'd dump to ~/backups/ and keeps the most recent $KEEP_DAYS.
set -euo pipefail

KEEP_DAYS="${KEEP_DAYS:-14}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # backend/
env_file="$here/.env"

if [[ -z "${DATABASE_URL:-}" && -f "$env_file" ]]; then
    DATABASE_URL="$(grep -E '^DATABASE_URL=' "$env_file" | head -n1 | cut -d= -f2-)"
fi
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "$(date +%FT%T) backup_db: DATABASE_URL not set (checked $env_file)" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
out="$BACKUP_DIR/form4_$(date +%F_%H%M%S).sql.gz"

pg_dump "$DATABASE_URL" | gzip > "$out"
echo "$(date +%FT%T) backup_db: wrote $out ($(du -h "$out" | cut -f1))"

# Prune old dumps.
find "$BACKUP_DIR" -name 'form4_*.sql.gz' -type f -mtime "+$KEEP_DAYS" -print -delete
