"""Upsert normalized Form 4 records into ``form4_transactions``.

Shared by the quarterly bulk backfill (SCRUM-44) and the nightly EDGAR
ingest (SCRUM-45). Two keys are in play:

* ``(accession_no, trans_sk)`` -- the row natural key, for within-source
  idempotency: re-running either loader over the same input updates rows
  in place rather than duplicating them.
* ``accession_no`` -- the supersede unit *across* sources. The bulk data
  set carries SEC's real per-line surrogate key (``NONDERIV_TRANS_SK``);
  the nightly job can only synthesize one, so ``bulk`` and ``edgar`` rows
  for the same filing never share ``trans_sk``. Instead: a ``bulk`` load
  deletes any ``edgar`` rows for the filings it touches, and the ``edgar``
  job skips any filing already covered by ``bulk``. Authoritative
  quarterly data always wins.
"""

from collections import OrderedDict

# Column order for both the INSERT and each value tuple. ``source`` is
# supplied by the caller, not read from the record.
_DATA_COLUMNS = (
    "issuer_ticker",
    "issuer_cik",
    "issuer_name",
    "insider_name",
    "insider_cik",
    "transaction_code",
    "transaction_date",
    "filing_date",
    "shares",
    "price",
    "accession_no",
    "trans_sk",
)
_ALL_COLUMNS = _DATA_COLUMNS + ("source",)
_UPDATABLE = tuple(c for c in _ALL_COLUMNS if c not in ("accession_no", "trans_sk"))

_UPSERT = f"""
    INSERT INTO form4_transactions ({", ".join(_ALL_COLUMNS)})
    VALUES ({", ".join(["%s"] * len(_ALL_COLUMNS))})
    ON CONFLICT (accession_no, trans_sk) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in _UPDATABLE)},
        ingested_at = now()
"""

VALID_SOURCES = ("bulk", "edgar")


def upsert_transactions(conn, records, source, *, batch_size=1000):
    """Upsert ``records`` (dicts from ``form4_ingest.bulk.parse_source`` or
    ``form4_ingest.edgar.normalize_filing``) tagged with ``source``.

    Runs on ``conn`` without committing -- the caller owns the transaction.
    Returns the number of rows written (after the cross-source supersede
    rules have been applied).
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}")

    records = list(records)
    accessions = list(OrderedDict.fromkeys(record["accession_no"] for record in records))
    if not accessions:
        return 0

    with conn.cursor() as cur:
        if source == "bulk":
            # Authoritative: drop stale edgar rows for these filings first.
            cur.execute(
                "DELETE FROM form4_transactions "
                "WHERE source = 'edgar' AND accession_no = ANY(%s)",
                (accessions,),
            )
            rows = records
        else:
            covered = {
                row[0]
                for row in cur.execute(
                    "SELECT DISTINCT accession_no FROM form4_transactions "
                    "WHERE source = 'bulk' AND accession_no = ANY(%s)",
                    (accessions,),
                ).fetchall()
            }
            rows = [record for record in records if record["accession_no"] not in covered]

        written = 0
        batch = []
        for record in rows:
            batch.append(tuple(record.get(column) for column in _DATA_COLUMNS) + (source,))
            if len(batch) >= batch_size:
                cur.executemany(_UPSERT, batch)
                written += len(batch)
                batch = []
        if batch:
            cur.executemany(_UPSERT, batch)
            written += len(batch)
    return written
