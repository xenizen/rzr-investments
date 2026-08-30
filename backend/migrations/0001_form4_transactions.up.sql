-- SCRUM-43 / epic SCRUM-42: normalized SEC Form 4 open-market transactions.
--
-- One row per non-derivative transaction line reported on a Form 4, loaded
-- from either the quarterly bulk data set (source = 'bulk', SCRUM-44) or
-- the nightly live-EDGAR ingest (source = 'edgar', SCRUM-45). The screener
-- reads this table instead of parsing filings live on each request
-- (SCRUM-46).

CREATE TABLE form4_transactions (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    issuer_ticker     TEXT        NOT NULL,
    issuer_cik        TEXT        NOT NULL,
    issuer_name       TEXT        NOT NULL DEFAULT '',

    insider_name      TEXT        NOT NULL DEFAULT '',
    insider_cik       TEXT        NOT NULL DEFAULT '',

    transaction_code  TEXT        NOT NULL CHECK (transaction_code IN ('P', 'S')),
    transaction_date  DATE        NOT NULL,
    filing_date       DATE        NOT NULL,

    shares            NUMERIC     NOT NULL,
    price             NUMERIC,

    accession_no      TEXT        NOT NULL,
    -- SEC's NONDERIV_TRANS_SK for bulk rows. The nightly ingest synthesizes
    -- a stable per-filing sequence when it parses the XML (SCRUM-45), so
    -- this is TEXT rather than a number -- both shapes fit.
    trans_sk          TEXT        NOT NULL,

    source            TEXT        NOT NULL CHECK (source IN ('bulk', 'edgar')),
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Guards against a duplicate transaction line within one load batch.
    -- Cross-load, the loaders replace each touched filing's rows wholesale
    -- rather than upserting on this key (see form4_ingest/store.py).
    CONSTRAINT form4_transactions_natural_key UNIQUE (accession_no, trans_sk)
);

-- Screener query: "issuer X's transactions since date D" and per-ticker
-- aggregation (SCRUM-46).
CREATE INDEX form4_transactions_ticker_date_idx
    ON form4_transactions (issuer_ticker, transaction_date);

-- Screener query: "all P (or S) transactions since date D" -- the
-- market-wide scan behind the direction filter.
CREATE INDEX form4_transactions_code_date_idx
    ON form4_transactions (transaction_code, transaction_date);
