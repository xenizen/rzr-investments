"""Upsert normalized Form 4 records into ``form4_transactions``.

Shared by the quarterly bulk backfill (SCRUM-44) and the nightly EDGAR
ingest (SCRUM-45).

``accession_no`` is the unit of replacement. Each load, per filing it
touches, deletes the existing rows for that filing and writes the new set:

* a ``bulk`` load replaces both ``bulk`` and ``edgar`` rows for its
  filings (authoritative quarterly data wins);
* an ``edgar`` load skips any filing already covered by ``bulk``, and for
  the rest replaces prior ``edgar`` rows.

Replacing per filing -- rather than upserting on ``(accession_no,
trans_sk)`` -- keeps the two sources' incompatible surrogate keys from
piling up: bulk carries SEC's real ``NONDERIV_TRANS_SK`` while the nightly
job can only synthesize one from row position, so a filing re-parsed with a
different market-trade order would otherwise leave stale rows behind and
double-count. The ``(accession_no, trans_sk)`` unique constraint still
guards against a duplicate line within one batch.
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

_INSERT = f"""
    INSERT INTO form4_transactions ({", ".join(_ALL_COLUMNS)})
    VALUES ({", ".join(["%s"] * len(_ALL_COLUMNS))})
    ON CONFLICT (accession_no, trans_sk) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in _UPDATABLE)},
        ingested_at = now()
"""

VALID_SOURCES = ("bulk", "edgar")


def upsert_transactions(conn, records, source, *, batch_size=1000):
    """Load ``records`` (dicts from ``form4_ingest.bulk.parse_source`` or
    ``form4_ingest.edgar.normalize_filing``) tagged with ``source``.

    Per filing touched, the existing rows are deleted and the new set
    written -- see the module docstring for why replacement rather than
    key-wise upsert. Runs on ``conn`` without committing (the caller owns
    the transaction). Returns the number of rows written.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}")

    records = list(records)
    accessions = list(OrderedDict.fromkeys(record["accession_no"] for record in records))
    if not accessions:
        return 0

    with conn.cursor() as cur:
        if source == "edgar":
            # Bulk data is authoritative -- leave any bulk-covered filing be.
            covered = {
                row[0]
                for row in cur.execute(
                    "SELECT DISTINCT accession_no FROM form4_transactions "
                    "WHERE source = 'bulk' AND accession_no = ANY(%s)",
                    (accessions,),
                ).fetchall()
            }
            rows = [record for record in records if record["accession_no"] not in covered]
            replace = [accession for accession in accessions if accession not in covered]
        else:  # bulk replaces whatever is there, bulk or edgar
            rows = records
            replace = accessions

        if replace:
            cur.execute(
                "DELETE FROM form4_transactions WHERE accession_no = ANY(%s)",
                (replace,),
            )

        written = 0
        batch = []
        for record in rows:
            batch.append(tuple(record.get(column) for column in _DATA_COLUMNS) + (source,))
            if len(batch) >= batch_size:
                cur.executemany(_INSERT, batch)
                written += len(batch)
                batch = []
        if batch:
            cur.executemany(_INSERT, batch)
            written += len(batch)
    return written
