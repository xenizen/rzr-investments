from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from edgar.exceptions import CompanyNotFoundError, ParsingError

from insider_data import (
    NAME_SEARCH_LIMIT,
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


def _search_result(insider_name, net_change, issuer, filing_date):
    """A mock SEC full-text search hit -- get_filing() returns a plain
    filing mock, same shape _load_filing already knows how to consume."""
    result = MagicMock()
    result.get_filing.return_value = _filing(insider_name, net_change, issuer, filing_date)
    return result


def _name_search_factory_returning(total, results, capture=None):
    """A name_search_factory stand-in. If `capture` (a dict) is given, the
    exact (name, symbol, date_from, date_to) call args are recorded into it
    under those keys."""
    search = MagicMock()
    search.total = total
    search.results = results

    def factory(name, symbol, date_from, date_to):
        if capture is not None:
            capture.update(name=name, symbol=symbol, date_from=date_from, date_to=date_to)
        return search

    return factory


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
    results = [
        _search_result("Jane Doe", 100, "BKKT", date(2026, 8, 1)),
        _search_result("John Smith", 200, "BKKT", date(2026, 8, 2)),
    ]
    factory = _name_search_factory_returning(2, results)

    result = get_insider_data(symbol="BKKT", name="jane", name_search_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_name_filters_by_issuer_name():
    results = [
        _search_result("Jane Doe", 100, "Bakkt, Inc. (BKKT)", date(2026, 8, 1)),
        _search_result("John Smith", 200, "Acme Corp (ACME)", date(2026, 8, 2)),
    ]
    factory = _name_search_factory_returning(2, results)

    result = get_insider_data(symbol="BKKT", name="bakkt", name_search_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_symbol_and_name_are_anded():
    results = [_search_result("Jane Doe", 100, "BKKT", date(2026, 8, 1))]
    factory = _name_search_factory_returning(1, results)

    result = get_insider_data(symbol="BKKT", name="nomatch", name_search_factory=factory)

    assert result["results"] == []


def test_no_symbol_uses_name_search():
    results = [_search_result("Jane Doe", 100, "BKKT", date(2026, 8, 1))]
    factory = _name_search_factory_returning(1, results)

    result = get_insider_data(name="jane", name_search_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_name_search_scopes_by_symbol_and_date_range():
    captured = {}
    factory = _name_search_factory_returning(0, [], capture=captured)

    get_insider_data(symbol="bkkt", name="Jane", date_from="2026-01-01", date_to="2026-02-01", name_search_factory=factory)

    assert captured == {"name": "Jane", "symbol": "BKKT", "date_from": "2026-01-01", "date_to": "2026-02-01"}


def test_name_search_with_no_symbol_passes_none_for_ticker():
    captured = {}
    factory = _name_search_factory_returning(0, [], capture=captured)

    get_insider_data(name="Jane", name_search_factory=factory)

    assert captured["symbol"] == ""


def test_name_search_zero_matches_returns_empty_results_not_an_error():
    factory = _name_search_factory_returning(0, [])

    result = get_insider_data(name="nobody matches this", name_search_factory=factory)

    assert result == {"results": [], "page": 1, "page_size": PAGE_SIZE, "total_count": 0, "has_next": False}


def test_name_search_factory_error_returns_no_insider_data_found():
    def factory(name, symbol, date_from, date_to):
        raise CompanyNotFoundError(symbol)

    result = get_insider_data(name="Jane", name_search_factory=factory)

    assert result == {"error": NO_INSIDER_DATA_FOUND}


def test_name_search_total_count_reflects_true_matches_not_a_scan_cap():
    # The whole point of routing name searches through SEC's full-text
    # index (SCRUM-19): total_count is a real count of name matches, not an
    # upper bound on how many raw filings were scanned.
    results = [_search_result(f"Jane Doe {i}", i, "BKKT", date(2026, 8, 1)) for i in range(3)]
    factory = _name_search_factory_returning(3, results)

    result = get_insider_data(name="Jane Doe", name_search_factory=factory)

    assert result["total_count"] == 3
    assert result["has_next"] is False


def test_name_search_paginates_locally_over_the_fetched_batch():
    results = [_search_result(f"Insider {i}", i, "AAPL", date(2026, 8, 1)) for i in range(PAGE_SIZE + 5)]
    factory = _name_search_factory_returning(PAGE_SIZE + 5, results)

    page1 = get_insider_data(name="Insider", name_search_factory=factory)
    page2 = get_insider_data(name="Insider", page=2, name_search_factory=factory)

    assert len(page1["results"]) == PAGE_SIZE
    assert page1["has_next"] is True
    assert len(page2["results"]) == 5
    assert page2["has_next"] is False


def test_name_search_total_is_capped_at_name_search_limit():
    factory = _name_search_factory_returning(NAME_SEARCH_LIMIT + 500, [])

    result = get_insider_data(name="Common Name", name_search_factory=factory)

    assert result["total_count"] == NAME_SEARCH_LIMIT


def test_name_search_still_applies_local_name_filter_as_a_safety_net():
    # SEC's full-text search can return a filing that mentions the query
    # text somewhere without it actually being the insider or issuer name
    # by our stricter definition -- confirm that's still filtered out
    # rather than trusted blindly.
    results = [
        _search_result("Jane Doe", 100, "BKKT", date(2026, 8, 1)),
        _search_result("Someone Else", 200, "Unrelated Corp", date(2026, 8, 2)),
    ]
    factory = _name_search_factory_returning(2, results)

    result = get_insider_data(name="Jane", name_search_factory=factory)

    assert [r["insider_name"] for r in result["results"]] == ["Jane Doe"]


def test_name_search_clamps_a_future_end_date_to_today(monkeypatch):
    # A future end_date makes SEC's full-text search return zero results
    # (see _clamp_to_today) -- confirm the default name-search factory
    # clamps it before it ever reaches search_filings. Uses the real
    # search_filings dependency (patched) rather than name_search_factory,
    # since name_search_factory replaces _default_name_search entirely and
    # would bypass the clamping logic under test.
    captured = {}

    def fake_search_filings(query, forms, ticker, start_date, end_date, limit):
        captured["end_date"] = end_date
        search = MagicMock()
        search.total = 0
        search.results = []
        return search

    monkeypatch.setattr("insider_data.search_filings", fake_search_filings)

    far_future = f"{date.today().year + 10}-01-01"
    get_insider_data(name="Jane", date_to=far_future)

    assert captured["end_date"] == date.today().isoformat()


def test_name_search_leaves_a_past_end_date_alone(monkeypatch):
    captured = {}

    def fake_search_filings(query, forms, ticker, start_date, end_date, limit):
        captured["end_date"] = end_date
        search = MagicMock()
        search.total = 0
        search.results = []
        return search

    monkeypatch.setattr("insider_data.search_filings", fake_search_filings)

    get_insider_data(name="Jane", date_to="2020-06-15")

    assert captured["end_date"] == "2020-06-15"


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

    with patch("filing_loader.ThreadPoolExecutor") as mock_executor_cls:
        mock_executor = MagicMock()
        mock_executor.map.side_effect = RuntimeError("can't start new thread")
        mock_executor_cls.return_value = mock_executor

        result = get_insider_data(symbol="AAPL", company_factory=factory)

    assert len(result["results"]) == 3
    assert [r["insider_name"] for r in result["results"]] == ["Insider 2", "Insider 1", "Insider 0"]
