# Production database (SCRUM-50)

The screener reads Form 4 transactions from a PostgreSQL table
(`form4_transactions`, epic SCRUM-42). This is the runbook for standing that
database up on the production host and loading it.

**Host:** InMotion shared hosting (cPanel on CloudLinux, Passenger WSGI).
PostgreSQL and phpPgAdmin are pre-installed on all InMotion shared servers —
no add-on, no fallback needed.

**Model (decided SCRUM-50):** one database, one cPanel-prefixed user with
full rights on that database (not a superuser, scoped to the one DB). The
app, the migration runner, and the ingest jobs all connect as that user.
`DATABASE_URL` is delivered through `.env` at the app root on the server
(`$APP_ROOT/.env` — the server layout is flat, no `backend/` subdirectory;
see [deploying.md](deploying.md)), which the app loads via `env_setup`
(python-dotenv, `override=True`) — it is gitignored, so deploying tracked
files never overwrites it.

**As provisioned:**

| | |
| --- | --- |
| database | `robins67_rzr_invest` |
| user | `robins67_rzr_investr` |
| host / port | `localhost` / `5432` (not reachable off-box) |
| password | in the team vault |

---

## 1. Create the database (cPanel) — done

cPanel → **Databases → PostgreSQL Databases**: created the database and user
above and granted the user **ALL PRIVILEGES** on the database.

> **Postgres 15+ note.** cPanel's "ALL PRIVILEGES" grants rights on the
> *database* but not always `CREATE` on the `public` *schema*, which the
> migration needs. If `migrate.py up` (step 3) fails with *"permission
> denied for schema public"*, open **phpPgAdmin** (cPanel → PostgreSQL
> Databases → phpPgAdmin), select `robins67_rzr_invest`, and run in the SQL
> box:
>
> ```sql
> GRANT ALL ON SCHEMA public TO "robins67_rzr_investr";
> ALTER DEFAULT PRIVILEGES IN SCHEMA public
>   GRANT ALL ON TABLES TO "robins67_rzr_investr";
> ```

## 2. Point the app at it

SSH to the server (InMotion shared SSH is port 2222; confirm the hostname in
cPanel → *Server Information* — known value: `ecngx256.inmotionhosting.com`):

```bash
ssh -p 2222 robins67@ecngx256.inmotionhosting.com
cd ~/resumesite/investapp        # $APP_ROOT — where passenger_wsgi.py lives
```

Add the URL to `$APP_ROOT/.env` (create the file if the Alpaca keys aren't
already there):

```
DATABASE_URL=postgresql://robins67_rzr_investr:PASSWORD@localhost:5432/robins67_rzr_invest
```

If the cPanel password contains any of `@ : / ? # [ ] %`, either
percent-encode those characters in the URL **or** use libpq's keyword form
instead, which needs no encoding:

```
DATABASE_URL=host=localhost port=5432 dbname=robins67_rzr_invest user=robins67_rzr_investr password=PASSWORD
```

(Simplest: regenerate the cPanel user's password as letters+digits only.)

Install the Postgres driver into the app's virtualenv (cPanel → **Setup
Python App** shows the exact `source .../activate` command for this app):

```bash
source /home/robins67/virtualenv/resumesite/investapp/3.12/bin/activate
pip install -r requirements.txt      # psycopg[binary] is now in there
```

`psycopg[binary]` ships manylinux wheels; if the server's Python is too new
for a wheel, `pip install psycopg` (pure Python) works too — libpq is
present because PostgreSQL is installed on the box.

Restart the app (cPanel → Setup Python App → **Restart**, or `touch
$APP_ROOT/tmp/restart.txt`).

## 3. Apply the schema

Still over SSH, in `$APP_ROOT` with the virtualenv active:

```bash
python migrate.py status     # 0001_form4_transactions -> pending
python migrate.py up
python migrate.py status     # -> applied
```

The runner reads `DATABASE_URL` from `$APP_ROOT/.env` the same way the app
does. See [../README.md](../README.md#database-form-4-transaction-store).

## 4. Load Form 4 history

The quarterly bulk data sets are too big to keep in git. Copy them up and
run the backfill on the server (cPanel Postgres is localhost-only, so this
can't be driven from a laptop):

```bash
# from your machine (run once on the server: mkdir -p ~/resumesite/investapp/data/form345)
scp -P 2222 backend/data/form345/2026q?_form345.zip \
    robins67@ecngx256.inmotionhosting.com:~/resumesite/investapp/data/form345/

# on the server, venv active, in $APP_ROOT
python -m form4_ingest.backfill data/form345/2026q1_form345.zip data/form345/2026q2_form345.zip
```

Then close the gap from the last published quarter to today with the nightly
ingest — the first run is large, so bound it:

```bash
python -m form4_ingest.nightly --max-filings 0 --since 2026-07-01
```

Recurring scheduling of `form4_ingest.nightly` is SCRUM-49.

## 5. Backups

cPanel's Backup Wizard does include PostgreSQL databases, but add a daily
`pg_dump` for point-in-time control. cPanel → **Cron Jobs**:

```
15 4 * * *  cd ~/resumesite/investapp && ./scripts/backup_db.sh >> ~/logs/db-backup.log 2>&1
```

`scripts/backup_db.sh` dumps `DATABASE_URL` to `~/backups/` and keeps the
last 14 days. Review it before scheduling.

## 6. Verify end to end

```bash
# schema is there
psql "$DATABASE_URL" -c "\dt form4_transactions"
psql "$DATABASE_URL" -c "SELECT source, count(*) FROM form4_transactions GROUP BY source"

# the app connects and the screener query runs
curl -s "https://<site>/api/insider-screener?direction=Purchase&shares=10000&months=1" | head -c 400
```

A `503` with *"The screener is temporarily unavailable"* means the app
can't reach the DB — check `DATABASE_URL` in `$APP_ROOT/.env` and that the
app was restarted after editing it (`screener_errors.classify` logs the
real cause with a stack trace).

## Acceptance (SCRUM-50)

- [ ] Production app connects via `DATABASE_URL`; `form4_transactions` exists.
- [ ] Credentials in the vault, not the repo; DB user is not a superuser.
- [ ] `pg_dump` cron scheduled (and cPanel backups confirmed to cover PG).
- [ ] `/api/insider-screener` returns results end to end.
