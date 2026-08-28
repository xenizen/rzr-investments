"""Minimal forward/rollback SQL migration runner for the backend database.

Deliberately not Alembic: the backend has one table today (SCRUM-43) and a
short runway of schema changes ahead, so a directory of numbered
``.up.sql`` / ``.down.sql`` pairs plus this runner is enough. Revisit if the
schema starts changing often or needs data migrations.

Layout::

    backend/migrations/0001_form4_transactions.up.sql
    backend/migrations/0001_form4_transactions.down.sql

Usage (from ``backend/``, with ``DATABASE_URL`` set or in ``backend/.env``)::

    python migrate.py status        # show applied vs pending
    python migrate.py up            # apply every pending migration, in order
    python migrate.py down          # roll back the most recently applied one

Applied versions are tracked in a ``schema_migrations`` table. Each command
runs in a single transaction (see ``db.connection``): if a migration fails,
nothing from that run is committed.
"""

import sys
from pathlib import Path

import env_setup  # noqa: F401 -- load backend/.env before db reads DATABASE_URL

from db import connection

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def _ensure_tracking_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT PRIMARY KEY,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _applied_versions(conn):
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [row[0] for row in rows]


def _discover(direction):
    """``[(version, path), ...]`` for every ``*.<direction>.sql``, sorted by name."""
    suffix = f".{direction}.sql"
    return [
        (path.name[: -len(suffix)], path)
        for path in sorted(MIGRATIONS_DIR.glob(f"*{suffix}"))
    ]


def _pending(conn):
    applied = set(_applied_versions(conn))
    return [(v, p) for v, p in _discover("up") if v not in applied]


def cmd_status(conn):
    _ensure_tracking_table(conn)
    applied = set(_applied_versions(conn))
    known = {v for v, _ in _discover("up")}
    for version, _ in _discover("up"):
        print(f"  [{'applied' if version in applied else 'pending':>7}] {version}")
    for version in sorted(applied - known):
        print(f"  [{'applied':>7}] {version}  (no .up.sql file present)")


def cmd_up(conn):
    _ensure_tracking_table(conn)
    pending = _pending(conn)
    if not pending:
        print("Nothing to apply.")
        return
    for version, path in pending:
        print(f"Applying {version} ...")
        conn.execute(path.read_text())
        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
    print(f"Applied {len(pending)} migration(s).")


def cmd_down(conn):
    _ensure_tracking_table(conn)
    applied = _applied_versions(conn)
    if not applied:
        print("Nothing to roll back.")
        return
    version = applied[-1]
    down_path = MIGRATIONS_DIR / f"{version}.down.sql"
    if not down_path.exists():
        raise SystemExit(f"Cannot roll back {version}: {down_path.name} is missing.")
    print(f"Rolling back {version} ...")
    conn.execute(down_path.read_text())
    conn.execute("DELETE FROM schema_migrations WHERE version = %s", (version,))
    print(f"Rolled back {version}.")


COMMANDS = {"status": cmd_status, "up": cmd_up, "down": cmd_down}


def main(argv):
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print(f"usage: python migrate.py {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    with connection() as conn:
        COMMANDS[argv[0]](conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
