"""Parse SEC's quarterly Form 3/4/5 bulk data set (``form345``) into
normalized Form 4 transaction records (epic SCRUM-42, story SCRUM-44).

The data set ships one ZIP per quarter (``2026q1_form345.zip`` etc.),
~13 MB zipped, holding a set of ``.tsv`` tables. We use three:

* ``SUBMISSION.tsv``     -- one row per filing: accession, filing date,
                            document type, issuer CIK / name / ticker.
* ``REPORTINGOWNER.tsv`` -- one or more rows per filing: the insider(s).
* ``NONDERIV_TRANS.tsv`` -- one row per non-derivative transaction line.

``SUBMISSION`` and ``REPORTINGOWNER`` are small (tens of MB) and read into
dicts keyed by accession; ``NONDERIV_TRANS`` is streamed row by row and
joined against them, so peak memory doesn't scale with the transaction
file. That matters for a full-history backfill, less so for one quarter.

Output records match the shape ``screener.aggregate_by_issuer`` consumes,
plus ``trans_sk`` for the DB natural key::

    {issuer_ticker, issuer_cik, issuer_name, insider_name, insider_cik,
     transaction_code, transaction_date, filing_date, shares, price,
     accession_no, trans_sk}
"""

import csv
import io
import zipfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from form4_ingest.text import clean_cik, clean_ticker, coerce_number

# The screener's two directions map onto these Form 4 transaction codes.
# Every other code (F tax withholding, A grant, M option exercise, ...) is
# noise for a buy/sell signal.
KEPT_CODES = {"P", "S"}

# Form 4s only -- not Form 3 (initial), Form 5 (annual), or the ``/A``
# amendments. Mirrors edgartools' ``get_filings(form="4")`` in the live path
# (screener_data).
FORM4_DOCUMENT_TYPE = "4"

_TABLES = ("SUBMISSION.tsv", "REPORTINGOWNER.tsv", "NONDERIV_TRANS.tsv")

_MONTHS = {
    month: number
    for number, month in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
        start=1,
    )
}

# The tables we read have small cells, but other tables in the same set
# (FOOTNOTES) can exceed csv's 128 KB default; raise the ceiling once.
csv.field_size_limit(10 * 1024 * 1024)


class BulkSourceError(ValueError):
    """A ``form345`` source is missing, or missing one of the tables we need."""


@contextmanager
def _open_tables(source):
    """Yield ``{table_name: text_stream}`` for a form345 dir or ``.zip``."""
    source = Path(source)

    if source.is_dir():
        missing = [name for name in _TABLES if not (source / name).exists()]
        if missing:
            raise BulkSourceError(f"{source} is missing {', '.join(missing)}")
        handles = {name: (source / name).open(newline="", encoding="utf-8") for name in _TABLES}
        try:
            yield handles
        finally:
            for handle in handles.values():
                handle.close()
        return

    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            members = {Path(name).name: name for name in archive.namelist()}
            missing = [name for name in _TABLES if name not in members]
            if missing:
                raise BulkSourceError(f"{source} is missing {', '.join(missing)}")
            streams = {
                name: io.TextIOWrapper(
                    archive.open(members[name]), newline="", encoding="utf-8"
                )
                for name in _TABLES
            }
            try:
                yield streams
            finally:
                for stream in streams.values():
                    stream.close()
        return

    raise BulkSourceError(f"{source} is not a directory or a .zip file")


def _parse_date(value):
    """``31-MAR-2026`` -> ``date(2026, 3, 31)``. ``None`` if empty/malformed.

    Explicit month map rather than ``strptime('%d-%b-%Y')`` -- ``%b`` is
    locale-dependent and edgartools has had locale grief on this host.
    """
    value = (value or "").strip()
    if not value:
        return None
    try:
        day, month, year = value.split("-")
        return date(int(year), _MONTHS[month.upper()], int(day))
    except (ValueError, KeyError):
        return None


def _load_form4_submissions(stream):
    submissions = {}
    for row in csv.DictReader(stream, delimiter="\t"):
        if row.get("DOCUMENT_TYPE") == FORM4_DOCUMENT_TYPE:
            submissions[row["ACCESSION_NUMBER"]] = row
    return submissions


def _load_first_owners(stream):
    """First REPORTINGOWNER row per accession. Joint Form 4s are rare
    (<2% of filings) and the transaction tables don't say which owner acted,
    so attribute to the first -- matching the live path's ``owners[0]``."""
    owners = {}
    for row in csv.DictReader(stream, delimiter="\t"):
        owners.setdefault(row["ACCESSION_NUMBER"], row)
    return owners


def parse_source(source):
    """Yield normalized Form 4 P/S transaction records from one form345
    directory or ``.zip``.

    Rows that don't parse cleanly -- non-P/S code, non-Form-4 filing, no
    ticker, unparseable shares/date, missing surrogate key -- are skipped,
    not raised on. A missing/incomplete source raises ``BulkSourceError``.
    """
    with _open_tables(source) as tables:
        submissions = _load_form4_submissions(tables["SUBMISSION.tsv"])
        owners = _load_first_owners(tables["REPORTINGOWNER.tsv"])

        for row in csv.DictReader(tables["NONDERIV_TRANS.tsv"], delimiter="\t"):
            if row.get("TRANS_CODE") not in KEPT_CODES:
                continue

            accession = row["ACCESSION_NUMBER"]
            submission = submissions.get(accession)
            if submission is None:  # Form 3/5, an amendment, or unknown filing
                continue

            ticker = clean_ticker(submission.get("ISSUERTRADINGSYMBOL"))
            if not ticker:
                continue

            trans_sk = (row.get("NONDERIV_TRANS_SK") or "").strip()
            if not trans_sk:
                continue

            shares = coerce_number(row.get("TRANS_SHARES"))
            if shares is None or shares <= 0:
                continue

            transaction_date = _parse_date(row.get("TRANS_DATE"))
            filing_date = _parse_date(submission.get("FILING_DATE"))
            if transaction_date is None or filing_date is None:
                continue

            owner = owners.get(accession, {})
            yield {
                "issuer_ticker": ticker,
                "issuer_cik": clean_cik(submission.get("ISSUERCIK")),
                "issuer_name": (submission.get("ISSUERNAME") or "").strip(),
                "insider_name": (owner.get("RPTOWNERNAME") or "").strip(),
                "insider_cik": clean_cik(owner.get("RPTOWNERCIK")),
                "transaction_code": row["TRANS_CODE"],
                "transaction_date": transaction_date.isoformat(),
                "filing_date": filing_date.isoformat(),
                "shares": shares,
                "price": coerce_number(row.get("TRANS_PRICEPERSHARE")),
                "accession_no": accession,
                "trans_sk": trans_sk,
            }
