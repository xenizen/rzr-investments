# Deploying rzr-invest to production

**Host:** InMotion shared hosting — cPanel on CloudLinux, Passenger WSGI.
Code goes up with **rsync over SSH** (`ssh -p 2222
robins67@ecngx256.inmotionhosting.com`); database and one-off commands run
over the same connection. There is no CI/CD and no staging — the first
place a change runs is production.

The database side (PostgreSQL for the Form 4 store) has its own runbook:
[production-database.md](production-database.md). This page is the
whole-app checklist; step 3 below points back into that runbook.

### Server layout is flat

The repo's `backend/` **contents** are the Passenger app root on the
server — there is **no `backend/` subdirectory** up there. Throughout this
page:

```
APP_ROOT = ~/resumesite/investapp        # = /home/robins67/resumesite/investapp
```

So `backend/app.py` in the repo is `$APP_ROOT/app.py` on the server,
`backend/.env` is `$APP_ROOT/.env`, and the built frontend is served from
`$APP_ROOT/static/`. The web docroot for the subpath is a *different*
directory (`~/enochmgmt.com/investapp/`, where `.htaccess` lives) — see the
Passenger app-type gotcha below.

Run this list top to bottom for every deploy.

---

## 0. Pre-flight (local, on `main`)

- [ ] `git checkout main && git pull`
- [ ] `npm ci && npm test` — frontend suite passes
- [ ] `(cd backend && .venv/bin/python -m pytest -q)` — backend suite passes
- [ ] `npm run build` — regenerates `dist/`
- [ ] Have on hand: SSH creds (`:2222`), cPanel login, the DB password
      (team vault)
- [ ] If the Form 4 store needs (re)loading: the quarterly zips are at
      `backend/data/form345/{YYYY}q{N}_form345.zip`

## 1. Upload (rsync over SSH)

From the repo root. The trailing slash on `backend/` matters — it copies
the *contents* into `$APP_ROOT`, keeping the layout flat.

```bash
rsync -avz --delete -e 'ssh -p 2222' \
  --exclude='.venv/' --exclude='__pycache__/' --exclude='.pytest_cache/' \
  --exclude='data/' --exclude='static/' --exclude='.env' \
  --exclude='tests/' --exclude='stock_buy.py' \
  backend/  robins67@ecngx256.inmotionhosting.com:resumesite/investapp/

rsync -avz --delete -e 'ssh -p 2222' \
  dist/  robins67@ecngx256.inmotionhosting.com:resumesite/investapp/static/
```

- `static/`, `data/`, and `.env` are excluded, so `--delete` never removes
  the server's frontend build, downloaded quarter zips, or secrets.
- **Never upload `.env`.** The server's `$APP_ROOT/.env` holds
  `DATABASE_URL` and the Alpaca keys; it is gitignored and not in the local
  tree. It is also the *authoritative* copy — `env_setup.py` loads it with
  `override=True` so a value there wins over any stale key left in the
  host's app-server config.
- FTP works too if you prefer a client — same file mapping (repo `backend/`
  contents → `$APP_ROOT`, `dist/` → `$APP_ROOT/static/`), same exclusions.

## 2. Python dependencies (SSH)

cPanel → **Setup Python App** shows the exact `source .../activate` line
for this app.

```bash
cd $APP_ROOT
source /home/robins67/virtualenv/resumesite/investapp/3.12/bin/activate
pip install -r requirements.txt        # psycopg[binary], python-dotenv, ...
```

Install dependencies **before** restarting into the new code — a missing
`python-dotenv` or `psycopg` makes `app.py` fail on import and takes the
site down.

## 3. Database

Follow [production-database.md](production-database.md) §2–§4 (with the
virtualenv active, in `$APP_ROOT`):

- [ ] `$APP_ROOT/.env` on the server has `DATABASE_URL=...`
- [ ] `python migrate.py status` → `python migrate.py up` → `status`
      (0001_form4_transactions applied). If it fails with *"permission
      denied for schema public"*, run the `GRANT` from the runbook's §1
      note in phpPgAdmin.
- [ ] `scp -P 2222` the `form345` quarter zips to
      `$APP_ROOT/data/form345/`, then
      `python -m form4_ingest.backfill data/form345/2026q1_form345.zip data/form345/2026q2_form345.zip`
- [ ] `python -m form4_ingest.nightly --max-filings 0 --since <first-day-after-newest-quarter>`
      — gap-fill from the last published quarter to today. Large one-off
      run; CloudLinux resource limits can kill it, in which case let the
      nightly cron (step 5) walk the rest of the backlog forward.
- [ ] `psql "$DATABASE_URL" -c "SELECT source, count(*) FROM form4_transactions GROUP BY source"`

Skip this section entirely on deploys that don't change the schema or need
fresh history — the nightly cron (step 5) keeps the store current.

## 4. Restart & smoke test

- [ ] Restart: cPanel → Setup Python App → **Restart**, or
      `touch $APP_ROOT/tmp/restart.txt`
- [ ] `curl -A "Mozilla/5.0" "https://www.enochmgmt.com/investapp/api/stock-price?symbol=AAPL"` — regression: a price
- [ ] `curl -A "Mozilla/5.0" "https://www.enochmgmt.com/investapp/api/insider-data?symbol=AAPL"` — regression: results
- [ ] `curl -A "Mozilla/5.0" "https://www.enochmgmt.com/investapp/api/insider-screener?direction=Purchase&shares=10000&months=1"`
      — a `{results: [...], total_count: N, ...}` envelope
- [ ] Browser: site → **Screener** tab → *Run screen* → table renders,
      pagination works
- [ ] Tail the app error log — no tracebacks

The `-A "Mozilla/5.0"` is not optional: ModSecurity on this host returns
**406 Not Acceptable** to a `curl`/blank User-Agent (see the gotcha
section).

Only cPanel → Setup Python App → **Restart** regenerates the
cPanel-injected environment; `touch tmp/restart.txt` recycles the workers
but leaves stale host env vars in place. After editing `.env` or clearing a
bad host var, use the cPanel button.

A `503` *"The screener is temporarily unavailable"* means the app can't
reach the DB (`screener_errors.classify` logs the real cause with a
trace) — check `DATABASE_URL` and that the app was restarted after editing
`.env`.

## 5. Cron (same day, once)

cPanel → **Cron Jobs**, or `crontab -e` over SSH. Everything runs from
`$APP_ROOT` (flat — the scripts are at `$APP_ROOT/scripts/`).

```cron
MAILTO="you@example.com"
SHELL="/bin/bash"
PYTHON=/home/robins67/virtualenv/resumesite/investapp/3.12/bin/python

# PostgreSQL backup — docs/production-database.md §5
15 4 * * *  cd /home/robins67/resumesite/investapp && ./scripts/backup_db.sh >> /home/robins67/logs/db-backup.log 2>&1

# Nightly Form 4 ingest + staleness alarm — docs/form4-ingest-ops.md
30 5 * * *  /home/robins67/resumesite/investapp/scripts/nightly_ingest.sh
0  9 * * *  /home/robins67/resumesite/investapp/scripts/check_ingest_fresh.sh
```

`nightly_ingest.sh` is silent on success and emails the log tail on
failure; `check_ingest_fresh.sh` emails if there's been no successful run
in 48h. Set `MAILTO` to a real address (a blank/`""` `MAILTO` silences the
failure mail). Recovery and the new-quarter procedure are in
[form4-ingest-ops.md](form4-ingest-ops.md).

## 6. Wrap up

- [ ] Move the deployed SCRUM stories to **Done**
- [ ] Note the deploy in the team channel

---

## Serving path & the Passenger app-type gotcha

The app is served at **`www.enochmgmt.com/investapp/`** (a subpath, not a
domain root). `vite.config.js` already sets `base: '/investapp/'` for
`vite build`, and Flask's routes are relative, so no code changes are
needed — but the cPanel wiring has a trap:

- In **Setup Python App**, the `investapp` entry must have **Application
  startup file** `passenger_wsgi.py` and **Entry point** `application`
  filled in. If they're blank when you save the Application URL, cPanel
  writes a typeless Passenger config.
- With no explicit app type, Passenger auto-detects and picks **Node**,
  failing with `Cannot find module '.../app.js'` (then, once nudged,
  `SyntaxError: Unexpected token 'import'` on `passenger_wsgi.py`).
- Fix: the docroot `.htaccess`
  (`~/enochmgmt.com/investapp/.htaccess`) must contain:

  ```
  PassengerAppType wsgi
  PassengerStartupFile passenger_wsgi.py
  ```

  Append them if missing, then `touch ~/resumesite/investapp/tmp/restart.txt`.
- **cPanel's "Restart" button regenerates this `.htaccess` and has stripped
  those lines before.** After any Setup-Python-App save, re-check the
  `.htaccess`; if you only need to recycle workers, use the
  `tmp/restart.txt` touch-file instead.
- ModSecurity on this host returns **406 Not Acceptable** to requests with
  a `curl`/blank User-Agent. Smoke-test with `curl -A "Mozilla/5.0" ...`.

## Rollback

- **App:** re-run the step 1 rsync from the previous `main` (and that
  commit's `npm run build` output for `dist/` → `$APP_ROOT/static/`), then
  restart.
- The screener returning `503` while the initial backfill runs is
  **expected**, not a rollback trigger.
- **Roll back only if:** `/api/stock-price` or `/api/insider-data` regress,
  or the app fails to boot after restart.
- **DB:** `python migrate.py down` drops `form4_transactions`. Only needed
  if the migration itself is at fault — otherwise leave the table in place;
  the old code doesn't touch it.
