from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest
from edgar.exceptions import EdgarError

from screener_data import SCAN_LIMIT, get_insider_transactions

TODAY = date(2026, 8, 27)


def _filing(rows, *, ticker="AAPL", issuer_cik="0000320193", issuer_name="Apple Inc.",
            insider_name="Jane Doe", insider_cik="0001111111",
            filing_date="2026-08-25", accession_no="0000000000-26-000001", obj_raises=None):
    filing = MagicMock()
    filing.filing_date = date.fromisoformat(filing_date)
    filing.accession_no = accession_no

    if obj_raises is not None:
        filing.obj.side_effect = obj_raises
        return filing

    form4 = MagicMock()
    form4.market_trades = pd.DataFrame(rows) if rows else pd.DataFrame()
    # MagicMock treats `name=` in the constructor as the mock's own name, not
    # a `.name` attribute -- set it explicitly.
    issuer = MagicMock(ticker=ticker, cik=issuer_cik)
    issuer.name = issuer_name
    form4.issuer = issuer
    form4.insider_name = insider_name
    owner = MagicMock(cik=insider_cik)
    owner.name = insider_name
    form4.reporting_owners = [owner]
    filing.obj.return_value = form4
    return filing


def _factory(filings):
    calls = {}

    def factory(filing_date_range):
        calls["range"] = filing_date_range
        return filings

    factory.calls = calls
    return factory


def _run(filings, **kwargs):
    kwargs.setdefault("today", TODAY)
    return get_insider_transactions(filings_factory=_factory(filings), **kwargs)


def test_normalizes_purchase_rows_into_records():
    filings = [
        _filing([{"Date": "2026-08-10", "Shares": 10000, "Price": 50.0, "Code": "P"}]),
    ]

    records = _run(filings, direction="Purchase", months=2)

    assert records == [
        {
            "issuer_ticker": "AAPL",
            "issuer_cik": "0000320193",
            "issuer_name": "Apple Inc.",
            "insider_name": "Jane Doe",
            "insider_cik": "0001111111",
            "transaction_code": "P",
            "transaction_date": "2026-08-10",
            "shares": 10000.0,
            "price": 50.0,
            "filing_date": "2026-08-25",
            "accession_no": "0000000000-26-000001",
        }
    ]


def test_direction_sold_selects_s_code_rows():
    filings = [
        _filing(
            [
                {"Date": "2026-08-10", "Shares": 100, "Price": 5.0, "Code": "P"},
                {"Date": "2026-08-11", "Shares": 200, "Price": 6.0, "Code": "S"},
            ]
        ),
    ]

    records = _run(filings, direction="Sold", months=2)

    assert [r["transaction_code"] for r in records] == ["S"]
    assert records[0]["shares"] == 200.0


def test_non_purchase_sale_codes_are_excluded():
    filings = [
        _filing(
            [
                {"Date": "2026-08-10", "Shares": 100, "Price": 0.0, "Code": "A"},  # award
                {"Date": "2026-08-10", "Shares": 100, "Price": 0.0, "Code": "F"},  # tax
                {"Date": "2026-08-10", "Shares": 100, "Price": 0.0, "Code": "G"},  # gift
            ]
        ),
    ]

    assert _run(filings, direction="Purchase", months=2) == []


def test_transactions_outside_the_window_are_excluded():
    # months=2 from 2026-08-27 -> window starts 2026-06-27.
    filings = [
        _filing(
            [
                {"Date": "2026-06-26", "Shares": 100, "Price": 1.0, "Code": "P"},  # day before window
                {"Date": "2026-06-27", "Shares": 200, "Price": 1.0, "Code": "P"},  # first day in window
                {"Date": "2026-08-27", "Shares": 300, "Price": 1.0, "Code": "P"},  # today (inclusive)
                {"Date": "2026-09-01", "Shares": 400, "Price": 1.0, "Code": "P"},  # future
            ]
        ),
    ]

    records = _run(filings, direction="Purchase", months=2)

    assert sorted(r["transaction_date"] for r in records) == ["2026-06-27", "2026-08-27"]


def test_window_start_tracks_the_months_parameter():
    filings = [
        _filing([{"Date": "2026-07-15", "Shares": 100, "Price": 1.0, "Code": "P"}]),
    ]

    # 1 month back -> window starts 2026-07-27, so a 2026-07-15 trade is out.
    assert _run(filings, direction="Purchase", months=1) == []
    # 3 months back -> window starts 2026-05-27, so it's in.
    assert len(_run(filings, direction="Purchase", months=3)) == 1


def test_multiple_rows_in_one_filing_become_multiple_records():
    filings = [
        _filing(
            [
                {"Date": "2026-08-10", "Shares": 100, "Price": 1.0, "Code": "P"},
                {"Date": "2026-08-12", "Shares": 200, "Price": 2.0, "Code": "P"},
            ]
        ),
    ]

    records = _run(filings, direction="Purchase", months=2)

    assert [r["shares"] for r in records] == [200.0, 100.0]  # newest transaction first


def test_records_are_sorted_newest_transaction_first_across_filings():
    filings = [
        _filing([{"Date": "2026-07-01", "Shares": 1, "Price": 1.0, "Code": "P"}], accession_no="a-1"),
        _filing([{"Date": "2026-08-01", "Shares": 2, "Price": 1.0, "Code": "P"}], accession_no="a-2"),
        _filing([{"Date": "2026-06-30", "Shares": 3, "Price": 1.0, "Code": "P"}], accession_no="a-3"),
    ]

    records = _run(filings, direction="Purchase", months=3)

    assert [r["transaction_date"] for r in records] == ["2026-08-01", "2026-07-01", "2026-06-30"]


def test_a_filing_that_fails_to_parse_is_skipped_not_fatal():
    filings = [
        _filing(None, obj_raises=EdgarError("boom"), accession_no="bad"),
        _filing([{"Date": "2026-08-10", "Shares": 100, "Price": 1.0, "Code": "P"}], accession_no="good"),
    ]

    records = _run(filings, direction="Purchase", months=2)

    assert [r["accession_no"] for r in records] == ["good"]


def test_shares_with_trailing_footnote_marker_are_parsed():
    filings = [
        _filing([{"Date": "2026-08-10", "Shares": "15000 F1", "Price": "12.5 F2", "Code": "P"}]),
    ]

    record = _run(filings, direction="Purchase", months=2)[0]

    assert record["shares"] == 15000.0
    assert record["price"] == 12.5


def test_filing_with_no_market_trades_yields_nothing():
    assert _run([_filing([])], direction="Purchase", months=2) == []


def test_empty_filings_list_returns_empty():
    assert _run([], direction="Purchase", months=2) == []


def test_invalid_direction_raises_value_error():
    with pytest.raises(ValueError):
        get_insider_transactions(direction="Hold", months=2, filings_factory=_factory([]))


@pytest.mark.parametrize("months", [0, 7, -1, "two", None])
def test_invalid_months_raises_value_error(months):
    with pytest.raises(ValueError):
        get_insider_transactions(direction="Purchase", months=months, filings_factory=_factory([]))


def test_requested_filing_date_range_matches_the_window():
    factory = _factory([])
    get_insider_transactions(direction="Purchase", months=2, filings_factory=factory, today=TODAY)
    assert factory.calls["range"] == "2026-06-27:2026-08-27"


def test_only_the_most_recent_scan_limit_filings_are_parsed():
    # SCAN_LIMIT + 5 filings; the oldest 5 by filing_date must be dropped
    # before parsing. Give each a distinct filing_date and a single in-window
    # trade so surviving count is observable.
    filings = []
    for i in range(SCAN_LIMIT + 5):
        day = 1 + (i % 27)
        filings.append(
            _filing(
                [{"Date": f"2026-08-{day:02d}", "Shares": 100, "Price": 1.0, "Code": "P"}],
                filing_date=f"2026-08-{day:02d}",
                accession_no=f"a-{i}",
            )
        )

    records = _run(filings, direction="Purchase", months=2)

    assert len(records) == SCAN_LIMIT
