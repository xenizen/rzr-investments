"""PostgreSQL connection helper for the Form 4 transaction store (epic SCRUM-42).

Everything that touches the database goes through here -- the migration
runner (SCRUM-43), the quarterly bulk backfill (SCRUM-44), the nightly
EDGAR ingest (SCRUM-45), and the screener's DB query path (SCRUM-46) -- so
there is one place that knows how to build a connection.

Configuration is a single ``DATABASE_URL`` (a libpq connection URL), read
from the environment. ``env_setup`` loads ``backend/.env`` for local dev
and tests; deployment sets the real variable through the WSGI host.
"""

import os
from contextlib import contextmanager

import psycopg

DATABASE_URL_ENV = "DATABASE_URL"


class DatabaseNotConfigured(RuntimeError):
    """``DATABASE_URL`` is not set, so no connection can be built.

    Kept distinct from psycopg's own errors (a connection that was attempted
    and failed): this one never leaves the process.
    """


def database_url():
    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        raise DatabaseNotConfigured(
            f"{DATABASE_URL_ENV} is not set. Copy backend/.env.example to "
            "backend/.env and fill it in, or export it in the environment."
        )
    return url


def connect(**kwargs):
    """Open a new connection. The caller closes and commits it.

    ``kwargs`` pass straight through to ``psycopg.connect`` (e.g.
    ``autocommit=True``).
    """
    return psycopg.connect(database_url(), **kwargs)


@contextmanager
def connection(**kwargs):
    """Context-managed connection: commit on a clean exit, roll back on error."""
    conn = connect(**kwargs)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
