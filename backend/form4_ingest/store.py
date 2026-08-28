"""Upsert normalized Form 4 records into ``form4_transactions``.

Shared by the quarterly bulk backfill (SCRUM-44) and the nightly EDGAR
ingest (SCRUM-45). The conflict clause encodes the supersede rule: once a
``bulk`` row is written for a transaction line, only another ``bulk`` row
replaces it -- the nightly ``edgar`` pass never clobbers authoritative
quarterly data for the same ``(accession_no, trans_sk)``.
"""

# Column order used for both the INSERT and the per-record value tuple.
# ``source`` is appended by the caller, not taken from the record.
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
    WHERE form4_transactions.source <> 'bulk' OR EXCLUDED.source = 'bulk'
"""

VALID_SOURCES = ("bulk", "edgar")


def upsert_transactions(conn, records, source, *, batch_size=1000):
    """Upsert ``records`` (dicts from ``form4_ingest.bulk.parse_source`` or
    the nightly parser) tagged with ``source``.

    Runs on ``conn`` but does not commit -- the caller owns the transaction.
    Returns the number of records sent to the database.
    """
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}")

    sent = 0
    batch = []
    with conn.cursor() as cur:
        for record in records:
            batch.append(tuple(record.get(c) for c in _DATA_COLUMNS) + (source,))
            if len(batch) >= batch_size:
                cur.executemany(_UPSERT, batch)
                sent += len(batch)
                batch = []
        if batch:
            cur.executemany(_UPSERT, batch)
            sent += len(batch)
    return sent
