from unittest.mock import MagicMock

from edgar.exceptions import CompanyNotFoundError

from insider_data import (
    MAX_RESULTS,
    NO_CRITERIA_ENTERED,
    NO_INSIDER_DATA_FOUND,
    get_insider_data,
)


def _filing(insider_name, net_change, issuer, filing_date):
    summary = MagicMock(insider_name=insider_name, net_change=net_change, issuer=issuer)
    form4 = MagicMock()
    form4.get_ownership_summary.return_value = summary
    filing = MagicMock(filing_date=filing_date)
    filing.obj.return_value = form4
    return filing


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
    filings = [_filing("Jane Doe", 10000, "BKKT", "2026-08-01")]
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
        "has_more": False,
    }


def test_symbol_with_no_filings_returns_empty_results():
    factory = _company_factory_returning([])

    result = get_insider_data(symbol="ZZZZZ", company_factory=factory)

    assert result == {"results": [], "has_more": False}


def test_filings_without_a_form4_object_are_skipped():
    empty_filing = MagicMock()
    empty_filing.obj.return_value = None
    factory = _company_factory_returning([empty_filing])

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert result == {"results": [], "has_more": False}


def test_caps_results_at_max_results_and_flags_has_more():
    filings = [_filing(f"Insider {i}", i, "AAPL", "2026-08-01") for i in range(MAX_RESULTS + 5)]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert len(result["results"]) == MAX_RESULTS
    assert result["has_more"] is True


def test_exactly_max_results_reports_no_more():
    filings = [_filing(f"Insider {i}", i, "AAPL", "2026-08-01") for i in range(MAX_RESULTS)]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert len(result["results"]) == MAX_RESULTS
    assert result["has_more"] is False


def test_unknown_symbol_returns_no_insider_data_found():
    def factory(symbol):
        raise CompanyNotFoundError(symbol)

    result = get_insider_data(symbol="ZZZZZ", company_factory=factory)

    assert result == {"error": NO_INSIDER_DATA_FOUND}


def test_name_filters_by_insider_name():
    filings = [
        _filing("Jane Doe", 100, "BKKT", "2026-08-01"),
        _filing("John Smith", 200, "BKKT", "2026-08-02"),
    ]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="BKKT", name="jane", company_factory=factory)

    assert result == {
        "results": [
            {"insider_name": "Jane Doe", "net_change": 100, "issuer": "BKKT", "filing_date": "2026-08-01"}
        ],
        "has_more": False,
    }


def test_name_filters_by_issuer_name():
    filings = [
        _filing("Jane Doe", 100, "Bakkt, Inc. (BKKT)", "2026-08-01"),
        _filing("John Smith", 200, "Acme Corp (ACME)", "2026-08-02"),
    ]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="BKKT", name="bakkt", company_factory=factory)

    assert result == {
        "results": [
            {
                "insider_name": "Jane Doe",
                "net_change": 100,
                "issuer": "Bakkt, Inc. (BKKT)",
                "filing_date": "2026-08-01",
            }
        ],
        "has_more": False,
    }


def test_symbol_and_name_are_anded():
    filings = [_filing("Jane Doe", 100, "BKKT", "2026-08-01")]
    factory = _company_factory_returning(filings)

    result = get_insider_data(symbol="BKKT", name="nomatch", company_factory=factory)

    assert result == {"results": [], "has_more": False}


def test_no_symbol_uses_global_filings_search():
    filings = [_filing("Jane Doe", 100, "BKKT", "2026-08-01")]
    global_factory = _global_factory_returning(filings)

    result = get_insider_data(name="jane", global_filings_factory=global_factory)

    assert result == {
        "results": [
            {"insider_name": "Jane Doe", "net_change": 100, "issuer": "BKKT", "filing_date": "2026-08-01"}
        ],
        "has_more": False,
    }


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
