# rzr-invest

React (Vite) app for rzr-investing, with a Flask backend under `backend/`.

## Development

```bash
npm install
npm run dev
```

The dev server proxies `/api` to the Flask backend on port 5001:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
FLASK_APP=app.py .venv/bin/flask run --port 5001
```

## Backend configuration

Set these in the backend's environment (shell, or the host's WSGI config).
For local dev, copy `backend/.env.example` to `backend/.env` and fill it in.

| Variable | Used by | Notes |
| --- | --- | --- |
| `ALPACA_API_KEY` | stock price, insider screener | Alpaca **paper** account key. |
| `ALPACA_SECRET_KEY` | stock price, insider screener | Alpaca paper account secret. |
| `EDGAR_IDENTITY` | insider data, insider screener | `name email` string SEC EDGAR requires on every request. Defaults to a placeholder if unset. |
| `DATABASE_URL` | Form 4 transaction store (epic SCRUM-42) | libpq URL for the PostgreSQL database the bulk ingest writes to and the screener reads from. |

The insider screener (epic SCRUM-29) uses Alpaca for read-only market data
and paper-account context only; it never places orders, and the trading
client is pinned to Alpaca's paper environment.

## Database (Form 4 transaction store)

Epic SCRUM-42 stores normalized SEC Form 4 transactions in PostgreSQL. One-time
local setup, with PostgreSQL installed and running:

```bash
createdb rzr_invest
psql rzr_invest <<'SQL'
CREATE ROLE rzr_invest WITH LOGIN PASSWORD 'rzr_invest';
GRANT ALL ON SCHEMA public TO rzr_invest;
ALTER DATABASE rzr_invest OWNER TO rzr_invest;
SQL
```

That matches the `DATABASE_URL` in `.env.example`. In production the app
role should be least-privilege and separate from the migration role — see
SCRUM-50.

Apply the schema (and check migration state) with the runner:

```bash
cd backend
.venv/bin/python migrate.py status   # applied vs pending
.venv/bin/python migrate.py up       # apply pending migrations
.venv/bin/python migrate.py down     # roll back the most recent one
```

Migrations are numbered `.up.sql` / `.down.sql` pairs under
`backend/migrations/`; applied versions are tracked in a `schema_migrations`
table.
