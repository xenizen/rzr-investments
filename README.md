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
| `EDGAR_IDENTITY` | insider data, Form 4 ingest | `name email` string SEC EDGAR requires on every request. Defaults to a placeholder if unset. |
| `DATABASE_URL` | Form 4 transaction store (epic SCRUM-42) | libpq URL for the PostgreSQL database the bulk ingest writes to and the screener reads from. |

The insider screener (epic SCRUM-29) reads insider transactions from the
`form4_transactions` table (see below) — no SEC call on the request path.
It uses Alpaca for read-only market data and paper-account context only; it
never places orders, and the trading client is pinned to Alpaca's paper
environment.

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

### Backfilling Form 4 history

The screener reads insider transactions from `form4_transactions`. Seed it
from SEC's quarterly [Insider Transactions Data Sets](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets)
(`{YYYY}qN_form345.zip`). Download the quarters you need into
`backend/data/form345/` (gitignored), then:

```bash
cd backend
.venv/bin/python -m form4_ingest.backfill data/form345/2026q1_form345 data/form345/2026q2_form345
```

Accepts extracted directories or the `.zip` directly, and any number of
them. Re-running is safe — rows upsert on `(accession_no, trans_sk)`. Add
`--dry-run` to parse and count without writing. Only Form 4 `P`/`S`
(open-market purchase/sale) transactions are loaded.

Recent filings not yet covered by a published quarter are filled in by the
nightly EDGAR ingest.

### Nightly EDGAR ingest

The quarterly bulk set lags a quarter or more, so a nightly job pulls the
Form 4s filed since the newest stored one and upserts their P/S rows with
`source='edgar'`:

```bash
cd backend
.venv/bin/python -m form4_ingest.nightly            # newest stored filing_date -> today
.venv/bin/python -m form4_ingest.nightly --since 2026-07-01   # bound the first catch-up
.venv/bin/python -m form4_ingest.nightly --dry-run
```

Logs to stderr, exits non-zero on failure — wire it into cron (see
SCRUM-49). Idempotent: re-running over a window upserts in place. When a
new quarter is later backfilled, its `bulk` rows replace the `edgar` rows
for the same filings.

The **first** run against a table only seeded through a past quarter has a
months-wide window (tens of thousands of filings, an hour or more). Use
`--since` to walk it forward in chunks.
