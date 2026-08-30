"""Field-normalization helpers shared by the bulk and EDGAR parsers
(SCRUM-44 / SCRUM-45)."""

import math

import pytest

from form4_ingest.text import clean_cik, clean_ticker, coerce_number


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1295.0", 1295.0),          # bulk TSV cell
        ("15000", 15000.0),
        (1295.0, 1295.0),            # edgartools numeric scalar
        (15000, 15000.0),
        ("15000 F1", 15000.0),       # trailing footnote marker
        ("12.5 F2", 12.5),
        ("", None),
        ("   ", None),
        (None, None),
        ("n/a", None),               # no leading numeric run
        (float("nan"), None),
    ],
)
def test_coerce_number(value, expected):
    result = coerce_number(value)
    if expected is None:
        assert result is None
    else:
        assert result == expected
        assert not math.isnan(result)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0000320193", "320193"),    # SEC bulk zero-pads to 10 digits
        ("320193", "320193"),        # edgartools does not
        ("", ""),
        (None, ""),
        ("  0001214156 ", "1214156"),
        ("NOTANUMBER", "NOTANUMBER"),  # left alone if not all digits
    ],
)
def test_clean_cik(value, expected):
    assert clean_cik(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("aapl", "AAPL"),
        ("  brk.a ", "BRK.A"),
        ("", ""),
        (None, ""),
        ("NONE", ""),
        ("N/A", ""),
    ],
)
def test_clean_ticker(value, expected):
    assert clean_ticker(value) == expected
