"""Small field-normalization helpers shared by the bulk (SCRUM-44) and
nightly-EDGAR (SCRUM-45) parsers.

The two sources hand us the same facts in slightly different shapes -- bulk
TSV cells are always strings, edgartools DataFrame cells are numpy scalars
or footnote-tainted strings -- so these accept both.
"""

import itertools
import math


def coerce_number(value):
    """Leading numeric run of ``value`` as a float, or ``None``.

    Handles bulk's plain strings (``"1295.0"``, ``""``), edgartools' numeric
    scalars, footnote-tainted strings (``"15000 F1"``), ``NaN`` and ``None``.
    """
    if value is None:
        return None
    if isinstance(value, str):
        digits = "".join(itertools.takewhile(lambda c: c.isdigit() or c == ".", value.strip()))
        try:
            return float(digits) if digits else None
        except ValueError:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def clean_cik(value):
    """Canonicalize a CIK to its unpadded form.

    SEC's bulk data zero-pads CIKs to 10 digits; edgartools doesn't. Strip
    the padding so ``bulk`` and ``edgar`` rows for the same entity match.
    """
    value = (value or "").strip()
    return str(int(value)) if value.isdigit() else value


def clean_ticker(value):
    """Upper-case a ticker; treat blanks and ``NONE`` / ``N/A`` as missing."""
    value = (value or "").strip().upper()
    return "" if value in ("", "NONE", "N/A") else value
