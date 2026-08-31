# Deploying rzr-invest to production

**Host:** InMotion shared hosting — cPanel on CloudLinux, Passenger WSGI.
Code goes up by **FTP**; database and one-off commands are run over **SSH**
(port 2222). There is no CI/CD and no staging — the first place a change
runs is production.

The database side (PostgreSQL for the Form 4 store) has its own runbook:
[production-database.md](production-database.md). This page is the
whole-app checklist; step 3 below points back into that runbook.

Run this list top to bottom for every deploy.

---

## 0. Pre-flight (local, on `main`)

- [ ] `git checkout main && git pull`
- [ ] `npm ci && npm test` — frontend suite passes
- [ ] `(cd backend && .venv/bin/python -m pytest -q)` — backend suite passes
- [ ] `npm run build` — regenerates `dist/`
- [ ] Have on hand: FTP creds, SSH creds (`:2222`), cPanel login, the DB
      password (team vault)
- [ ] If the Form 4 store needs (re)loading: the quarterly zips are at
      `backend/data/form345/{YYYY}q{N}_form345.zip`

## 1. FTP upload

Upload to the server preserving paths under the app root:

- [ ] `backend/` — `*.py`, `migrations/`, `form4_ingest/`, `scripts/`,
      `requirements*.txt`.
      **Exclude:** `.venv/`, `static/`, `data/`, `.env`, `__pycache__/`,
      `.pytest_cache/` (and `tests/` if you want a lean prod tree).
- [ ] `dist/` contents → `backend/static/` on the server (overwrite — this
      is the built frontend).
- [ ] **Never upload `backend/.env`.** The server's copy holds
      `DATABASE_URL` and the Alpaca keys; it is gitignored so it is not in
      the local tree anyway.

## 2. Python dependencies (SSH)

cPanel → **Setup Python App** shows the exact `source .../activate` line
for this app.

```bash
cd ~/<app-root>/backend
pip install -r requirements.txt        # picks up psycopg[binary], python-dotenv
```

## 3. Database

Follow [production-database.md](production-database.md) §2–§4:

- [ ] `backend/.env` on the server has `DATABASE_URL=...`
- [ ] `python migrate.py status` → `python migrate.py up` → `status`
      (0001_form4_transactions applied). If it fails with *"permission
      denied for schema public"*, run the `GRANT` from the runbook's §1
      note in phpPgAdmin.
- [ ] `scp` the `form345` quarter zips up, then
      `python -m form4_ingest.backfill data/form345/2026q1_form345.zip data/form345/2026q2_form345.zip`
- [ ] `python -m form4_ingest.nightly --max-filings 0 --since <first-day-after-newest-quarter>`
      — gap-fill from the last published quarter to today. Large one-off run.
- [ ] `psql "$DATABASE_URL" -c "SELECT source, count(*) FROM form4_transactions GROUP BY source"`

Skip this section entirely on deploys that don't change the schema or need
fresh history — the nightly cron (step 5) keeps the store current.

## 4. Restart & smoke test

- [ ] Restart: cPanel → Setup Python App → **Restart**, or
      `touch ~/<app-root>/backend/tmp/restart.txt`
- [ ] `curl "https://<site>/api/stock-price?symbol=AAPL"` — regression: a price
- [ ] `curl "https://<site>/api/insider-data?symbol=AAPL"` — regression: results
- [ ] `curl "https://<site>/api/insider-screener?direction=Purchase&shares=10000&months=1"`
      — a `{results: [...], total_count: N, ...}` envelope
- [ ] Browser: site → **Screener** tab → *Run screen* → table renders,
      pagination works
- [ ] Tail the app error log — no tracebacks

A `503` *"The screener is temporarily unavailable"* means the app can't
reach the DB (`screener_errors.classify` logs the real cause with a
trace) — check `DATABASE_URL` and that the app was restarted after editing
`.env`.

## 5. Cron (same day, once)

cPanel → **Cron Jobs**. `<app-root>` is the deployed directory (the repo's
`backend/` contents, flattened); set `PYTHON` to the venv python from
cPanel → Setup Python App.

```cron
PYTHON=/home/robins67/virtualenv/resumesite/investapp/3.12/bin/python

# PostgreSQL backup — docs/production-database.md §5
15 4 * * *  cd <app-root> && ./scripts/backup_db.sh >> ~/logs/db-backup.log 2>&1

# Nightly Form 4 ingest + staleness alarm — docs/form4-ingest-ops.md
30 5 * * *  <app-root>/scripts/nightly_ingest.sh
0  9 * * *  <app-root>/scripts/check_ingest_fresh.sh
```

`nightly_ingest.sh` is silent on success and emails the log tail on
failure; `check_ingest_fresh.sh` emails if there's been no successful run
in 48h. Recovery and the new-quarter procedure are in
[form4-ingest-ops.md](form4-ingest-ops.md).

## 6. Wrap up

- [ ] Move the deployed SCRUM stories to **Done**
- [ ] Note the deploy in the team channel

---

## Rollback

- **App:** re-FTP the previous `main`'s `backend/` tree and the previous
  `dist/` → `backend/static/`, then restart.
- The screener returning `503` while the initial backfill runs is
  **expected**, not a rollback trigger.
- **Roll back only if:** `/api/stock-price` or `/api/insider-data` regress,
  or the app fails to boot after restart.
- **DB:** `python migrate.py down` drops `form4_transactions`. Only needed
  if the migration itself is at fault — otherwise leave the table in place;
  the old code doesn't touch it.
