# Form 4 ingest — operations (SCRUM-49)

How the `form4_transactions` store stays current, how to watch it, and how
to recover when something goes wrong. Companion to
[production-database.md](production-database.md) (first-time provisioning)
and [insider-screener-architecture.md](insider-screener-architecture.md)
(how the data is used).

## How the store is filled

| Source | Job | Cadence | Covers |
| --- | --- | --- | --- |
| `bulk` | `form4_ingest.backfill` (one-off, manual) | when SEC posts a quarter | whole quarters, authoritative |
| `edgar` | `form4_ingest.nightly` (cron) | nightly | the gap from the newest stored `filing_date` to today |

Each load **replaces every filing it touches** (delete by `accession_no`,
then insert). A `bulk` load wins over `edgar` for the same filing; the
`edgar` job skips filings already covered by `bulk`. So re-running either
job is always safe.

The nightly job caps itself at `--max-filings` (default 4000, ~5 days) and
takes whole days oldest-first, so after a long gap it converges over
several nights rather than firing tens of thousands of SEC fetches at once.

## Cron

cPanel → **Cron Jobs**. Set `PYTHON` to the app's virtualenv python (from
cPanel → Setup Python App), and `<app-root>` to the deployed directory.

```cron
PYTHON=/home/robins67/virtualenv/resumesite/investapp/3.12/bin/python

# Nightly incremental ingest — silent on success, emails on failure.
30 5 * * *  /home/robins67/resumesite/investapp/scripts/nightly_ingest.sh

# Staleness alarm — emails if no successful run in 48h.
0 9 * * *  /home/robins67/resumesite/investapp/scripts/check_ingest_fresh.sh
```

- `nightly_ingest.sh` appends everything to `~/logs/form4-nightly.log` and
  writes `~/.local/state/rzr-invest/nightly-ok` (unix ts) on success. It
  prints nothing on success, so cron only mails you when a run fails.
- `check_ingest_fresh.sh` reads that marker; if the last success is older
  than `MAX_AGE_HOURS` (48) it prints one line and exits 1, so cron mails.
- cPanel emails cron output to the account address by default. To send
  elsewhere, put `MAILTO=you@example.com` at the top of the cron block.

## Monitoring

- **Failed run:** cron email from `nightly_ingest.sh` with the log tail.
- **Silent stall** (cron disabled, host issue): cron email from
  `check_ingest_fresh.sh` within a day.
- **Content freshness** (is the *data* recent, vs. did the *job* run): the
  screener response carries `data_through` (newest `filing_date`), shown in
  the UI as "Insider data current through &lt;date&gt;". A few days' lag is
  normal (weekends, SEC processing); a week-plus means the nightly job has
  been failing — check the log.

## Recovery

**A nightly run failed.** Read `~/logs/form4-nightly.log`. Common causes:
SEC rate-limiting / transient network, or `DATABASE_URL` unset. Just re-run
it — the window is recomputed from the DB and the load is idempotent:

```bash
cd <app-root> && scripts/nightly_ingest.sh
```

**Catching up a large gap** (first run after a backfill, or days of
failures). Let the nightly cron walk it forward, or force it in one go:

```bash
$PYTHON -m form4_ingest.nightly --max-filings 0 --since <YYYY-MM-DD>
```

Run this detached (`nohup … &` or `screen`) — it can take an hour or more.

**Partial load.** There's no such thing to clean up: each run commits in
one transaction, so a crash mid-run rolls back and leaves the store as it
was. Re-run.

**A new quarter is published.** Download it and back it up — its `bulk`
rows replace whatever `edgar` rows the nightly job wrote for those filings:

```bash
cd <app-root>
curl -sS -A "$EDGAR_IDENTITY" -o data/form345/2026q3_form345.zip \
  https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2026q3_form345.zip
$PYTHON -m form4_ingest.backfill data/form345/2026q3_form345.zip
```

No need to touch the nightly job — its next run recomputes its window from
the new `max(filing_date)`.

## First-time backfill

Covered in [production-database.md](production-database.md) §4. Short
version: download the quarterly `*_form345.zip` files into
`data/form345/`, run `form4_ingest.backfill` on them, then one
`form4_ingest.nightly --max-filings 0 --since <first day after the newest
quarter>` to close the gap to today.
