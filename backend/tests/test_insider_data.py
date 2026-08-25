from unittest.mock import MagicMock

from edgar.exceptions import CompanyNotFoundError

from insider_data import NO_INSIDER_DATA_FOUND, NO_SYMBOL_ENTERED, get_insider_data


def _filing(insider_name, net_change, issuer, filing_date):
    summary = MagicMock(insider_name=insider_name, net_change=net_change, issuer=issuer)
    form4 = MagicMock()
    form4.get_ownership_summary.return_value = summary
    filing = MagicMock(filing_date=filing_date)
    filing.obj.return_value = form4
    return filing


def _factory_returning(filings):
    company = MagicMock()
    company.get_filings.return_value = filings
    return lambda symbol: company


def test_blank_symbol_returns_no_symbol_entered():
    assert get_insider_data("") == {"error": NO_SYMBOL_ENTERED}
    assert get_insider_data("   ") == {"error": NO_SYMBOL_ENTERED}
    assert get_insider_data(None) == {"error": NO_SYMBOL_ENTERED}


def test_known_symbol_returns_results():
    filings = [_filing("Jane Doe", 10000, "BKKT", "2026-08-01")]
    factory = _factory_returning(filings)

    result = get_insider_data("bkkt", company_factory=factory)

    assert result == {
        "results": [
            {
                "insider_name": "Jane Doe",
                "net_change": 10000,
                "issuer": "BKKT",
                "filing_date": "2026-08-01",
            }
        ]
    }


def test_symbol_with_no_filings_returns_empty_results():
    factory = _factory_returning([])

    result = get_insider_data("ZZZZZ", company_factory=factory)

    assert result == {"results": []}


def test_filings_without_a_form4_object_are_skipped():
    empty_filing = MagicMock()
    empty_filing.obj.return_value = None
    factory = _factory_returning([empty_filing])

    result = get_insider_data("AAPL", company_factory=factory)

    assert result == {"results": []}


def test_caps_results_at_max_filings():
    filings = [_filing(f"Insider {i}", i, "AAPL", "2026-08-01") for i in range(25)]
    factory = _factory_returning(filings)

    result = get_insider_data("AAPL", company_factory=factory)

    assert len(result["results"]) == 20


def test_unknown_symbol_returns_no_insider_data_found():
    def factory(symbol):
        raise CompanyNotFoundError(symbol)

    result = get_insider_data("ZZZZZ", company_factory=factory)

    assert result == {"error": NO_INSIDER_DATA_FOUND}
