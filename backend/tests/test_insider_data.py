from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from edgar.exceptions import CompanyNotFoundError, ParsingError

from insider_data import (
    NO_CRITERIA_ENTERED,
    NO_INSIDER_DATA_FOUND,
    PAGE_SIZE,
    SCAN_LIMIT,
    get_insider_data,
)


def _filing(insider_name, net_change, issuer, filing_date):
    summary = MagicMock(insider_name=insider_name, net_change=net_change, issuer=issuer)
    form4 = MagicMock()
    form4.get_ownership_summary.return_value = summary
    filing = MagicMock(filing_date=filing_date)
    filing.obj.return_value = form4
    return filing


def _dated_filings(count, start=date(2026, 8, 1)):
    """count filings, each one day older than the last, oldest first (so
    callers can assert on the sort reversing them to newest-first)."""
    return [
        _filing(f"Insider {i}", i, "AAPL", start - timedelta(days=count - 1 - i))
        for i in range(count)
    ]


def _company_factory_returning(filings):
    company = MagicMock()
    company.get_filings.return_value = filings
    return lambda symbol: company


def _global_factory_returning(filings):
    return lambda filing_date: filings


def test_blank_everything_returns_no_criteria_entered():
    assert get_insider_data() == {"error": NO_CRITERIA_ENTERED}
    assert get_insider_data(symbol="  ", name="", date_from="", date_to="") == {
        "error": NO_CRITERIA_ENTERED
    }


def test_known_symbol_returns_results():
    filings = [_filing("Jane Doe", 10000, "BKKT", date(2026, 8, 1))]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="bkkt", company_factory=factory)

    assert result == {
        "results": [
            {
                "insider_name": "Jane Doe",
                "net_change": 10000,
                "issuer": "BKKT",
                "filing_date": "2026-08-01",
            }
        ],
        "page": 1,
        "page_size": PAGE_SIZE,
        "total_count": 1,
        "has_next": False,
    }


def test_symbol_with_no_filings_returns_empty_results():
    factory = _company_factory_returning([])

    result = get_insider_data(symbol="ZZZZZ", company_factory=factory)

    assert result == {
        "results": [],
        "page": 1,
        "page_size": PAGE_SIZE,
        "total_count": 0,
        "has_next": False,
    }


def test_filings_without_a_form4_object_are_skipped():
    empty_filing = MagicMock(filing_date=date(2026, 8, 1))
    empty_filing.obj.return_value = None
    factory = _company_factory_returning([empty_filing])

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert result["results"] == []


def test_a_filing_that_fails_to_load_is_skipped_not_fatal():
    good = _filing("Jane Doe", 100, "AAPL", date(2026, 8, 2))
    broken = MagicMock(filing_date=date(2026, 8, 1))
    broken.obj.side_effect = ParsingError("malformed filing")
    factory = _company_factory_returning([good, broken])

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_a_filing_whose_summary_fails_to_load_is_skipped_not_fatal():
    good = _filing("Jane Doe", 100, "AAPL", date(2026, 8, 2))
    broken_form4 = MagicMock()
    broken_form4.get_ownership_summary.side_effect = ParsingError("malformed summary")
    broken = MagicMock(filing_date=date(2026, 8, 1))
    broken.obj.return_value = broken_form4
    factory = _company_factory_returning([good, broken])

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_a_filing_with_malformed_ownership_xml_is_skipped_not_fatal():
    # get_ownership_summary() indexes into the reportingOwner list with no
    # emptiness check, so a filing with no <reportingOwner> element raises a
    # plain IndexError -- confirm that's caught same as any other bad filing.
    good = _filing("Jane Doe", 100, "AAPL", date(2026, 8, 2))
    broken_form4 = MagicMock()
    broken_form4.get_ownership_summary.side_effect = IndexError("list index out of range")
    broken = MagicMock(filing_date=date(2026, 8, 1))
    broken.obj.return_value = broken_form4
    factory = _company_factory_returning([good, broken])

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_unknown_symbol_returns_no_insider_data_found():
    def factory(symbol):
        raise CompanyNotFoundError(symbol)

    result = get_insider_data(symbol="ZZZZZ", company_factory=factory)

    assert result == {"error": NO_INSIDER_DATA_FOUND}


def test_no_matching_filings_returns_empty_results_not_an_error():
    # Covers edgartools returning None for a query it can't satisfy (e.g. a
    # malformed date range) rather than raising -- shouldn't look like a
    # crash or an error, just "nothing found".
    factory = _company_factory_returning(None)

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert result == {
        "results": [],
        "page": 1,
        "page_size": PAGE_SIZE,
        "total_count": 0,
        "has_next": False,
    }


def test_name_filters_by_insider_name():
    filings = [
        _filing("Jane Doe", 100, "BKKT", date(2026, 8, 1)),
        _filing("John Smith", 200, "BKKT", date(2026, 8, 2)),
    ]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="BKKT", name="jane", company_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_name_filters_by_issuer_name():
    filings = [
        _filing("Jane Doe", 100, "Bakkt, Inc. (BKKT)", date(2026, 8, 1)),
        _filing("John Smith", 200, "Acme Corp (ACME)", date(2026, 8, 2)),
    ]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="BKKT", name="bakkt", company_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_symbol_and_name_are_anded():
    filings = [_filing("Jane Doe", 100, "BKKT", date(2026, 8, 1))]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="BKKT", name="nomatch", company_factory=factory)

    assert result["results"] == []


def test_no_symbol_uses_global_filings_search():
    filings = [_filing("Jane Doe", 100, "BKKT", date(2026, 8, 1))]
    global_factory = _global_factory_returning(filings)

    result = get_insider_data(name="jane", global_filings_factory=global_factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_no_symbol_passes_date_range_to_global_factory():
    captured = {}

    def global_factory(filing_date):
        captured["filing_date"] = filing_date
        return []

    get_insider_data(date_from="2026-01-01", date_to="2026-02-01", global_filings_factory=global_factory)

    assert captured["filing_date"] == "2026-01-01:2026-02-01"


def test_one_sided_date_from_is_closed_with_today():
    captured = {}

    def global_factory(filing_date):
        captured["filing_date"] = filing_date
        return []

    get_insider_data(date_from="2026-01-01", global_filings_factory=global_factory)

    assert captured["filing_date"].startswith("2026-01-01:")
    assert captured["filing_date"] != "2026-01-01:"


def test_one_sided_date_to_is_closed_with_start_of_year():
    captured = {}

    def global_factory(filing_date):
        captured["filing_date"] = filing_date
        return []

    get_insider_data(date_to="2026-02-01", global_filings_factory=global_factory)

    assert captured["filing_date"] == "2026-01-01:2026-02-01"


# --- Pagination (SCRUM-13) ---


def test_first_page_returns_up_to_page_size_newest_first():
    filings = _dated_filings(PAGE_SIZE + 5)  # oldest first, as the raw API might return them
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert len(result["results"]) == PAGE_SIZE
    assert result["page"] == 1
    assert result["page_size"] == PAGE_SIZE
    assert result["total_count"] == PAGE_SIZE + 5
    assert result["has_next"] is True
    # Newest (highest index, most recent date) filing comes first.
    assert result["results"][0]["net_change"] == PAGE_SIZE + 4
    assert result["results"][-1]["net_change"] == 5


def test_second_page_returns_the_next_slice():
    filings = _dated_filings(PAGE_SIZE + 5)
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="AAPL", page=2, company_factory=factory)

    assert len(result["results"]) == 5
    assert result["page"] == 2
    assert result["has_next"] is False
    assert result["results"][0]["net_change"] == 4
    assert result["results"][-1]["net_change"] == 0


def test_page_past_the_end_returns_empty_results_and_no_next():
    filings = _dated_filings(3)
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="AAPL", page=5, company_factory=factory)

    assert result["results"] == []
    assert result["has_next"] is False


def test_non_numeric_page_defaults_to_one():
    filings = _dated_filings(3)
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="AAPL", page="not-a-number", company_factory=factory)

    assert result["page"] == 1


def test_zero_or_negative_page_clamps_to_one():
    filings = _dated_filings(3)
    factory = _company_factory_returning(filings)

    assert get_insider_data(symbol="AAPL", page=0, company_factory=factory)["page"] == 1
    assert get_insider_data(symbol="AAPL", page=-2, company_factory=factory)["page"] == 1


# --- Scan cap (post-review hardening) ---


def test_scan_limit_caps_how_many_raw_filings_are_considered():
    # More raw filings than SCAN_LIMIT are available (e.g. a broad,
    # symbol-less search); total_count and pagination should be bounded by
    # SCAN_LIMIT rather than reflecting the full underlying set.
    filings = _dated_filings(SCAN_LIMIT + 50)
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert result["total_count"] == SCAN_LIMIT


def test_last_page_within_scan_limit_has_no_next():
    filings = _dated_filings(SCAN_LIMIT + 50)
    factory = _company_factory_returning(filings)
    last_page = SCAN_LIMIT // PAGE_SIZE

    result = get_insider_data(symbol="AAPL", page=last_page, company_factory=factory)

    assert result["has_next"] is False
    assert len(result["results"]) == PAGE_SIZE


def test_falls_back_to_sequential_loading_when_threads_are_unavailable():
    # Some shared hosts (CloudLinux CageFS-limited accounts) reject even one
    # extra OS thread with a plain RuntimeError -- confirm that degrades to
    # sequential loading instead of failing the whole request.
    filings = _dated_filings(3)
    factory = _company_factory_returning(filings)

    with patch("insider_data.ThreadPoolExecutor") as mock_executor_cls:
        mock_executor = MagicMock()
        mock_executor.map.side_effect = RuntimeError("can't start new thread")
        mock_executor_cls.return_value = mock_executor

        result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert len(result["results"]) == 3
    assert [r["insider_name"] for r in result["results"]] == ["Insider 2", "Insider 1", "Insider 0"]
