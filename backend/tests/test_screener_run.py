import pytest

import screener_repo
from screener_run import PAGE_SIZE, run_screen


def _txn(ticker, shares, insider_cik, *, code="P", accession, insider_name="Ins",
         tdate="2026-08-20", filing_date="2026-08-21", price=1.0):
    return {
        "issuer_ticker": ticker,
        "issuer_cik": f"cik-{ticker}",
        "issuer_name": f"{ticker} Inc.",
        "insider_name": insider_name,
        "insider_cik": insider_cik,
        "transaction_code": code,
        "transaction_date": tdate,
        "shares": float(shares),
        "price": price,
        "filing_date": filing_date,
        "accession_no": accession,
    }


# Four issuers: three multi-insider, one single. Shares and prices chosen so
# ranking (multi -> shares -> discount, ties on ticker) has one right answer.
RANKING_TXNS = [
    _txn("AAA", 20000, "a1", accession="aaa-1"),
    _txn("BBB", 5000, "b1", accession="bbb-1"),
    _txn("BBB", 5000, "b2", accession="bbb-2"),
    _txn("CCC", 15000, "c1", accession="ccc-1"),
    _txn("CCC", 15000, "c2", accession="ccc-2"),
    _txn("DDD", 15000, "d1", accession="ddd-1"),
    _txn("DDD", 15000, "d2", accession="ddd-2"),
]
RANKING_PRICES = {"AAA": 30.0, "BBB": 50.0, "CCC": 20.0, "DDD": 20.0}
RANKING_HIGHS = {t: 100.0 for t in RANKING_PRICES}


def _source(records):
    """Stand-in for screener_source.get_insider_transactions -- validates
    direction/months the same way the real DB source does, then returns
    fixed records."""
    def source(direction, *, months):
        screener_repo._validate_direction(direction)
        screener_repo._validate_months(months)
        source.calls.append((direction, months))
        return list(records)

    source.calls = []
    return source


def _lookup(mapping):
    return lambda tickers: {t: mapping[t] for t in tickers if t in mapping}


def _run(records, prices, highs, **kwargs):
    kwargs.setdefault("min_shares", 5000)
    kwargs.setdefault("pct_below_high", 50)
    return run_screen(
        transactions_source=_source(records),
        price_lookup=_lookup(prices),
        high_lookup=_lookup(highs),
        **kwargs,
    )


def test_ranks_multi_insider_then_volume_then_discount_then_ticker():
    result = _run(RANKING_TXNS, RANKING_PRICES, RANKING_HIGHS)

    # CCC & DDD: multi, 30k shares, 80% discount -> tie broken by ticker.
    # BBB: multi, 10k shares. AAA: single insider, last.
    assert [r["ticker"] for r in result["results"]] == ["CCC", "DDD", "BBB", "AAA"]
    assert result["total_count"] == 4
    assert result["total_pages"] == 1
    assert result["has_next"] is False


def test_row_shape_and_derived_fields():
    result = _run(RANKING_TXNS, RANKING_PRICES, RANKING_HIGHS, min_shares=5000)
    ccc = result["results"][0]

    assert ccc == {
        "ticker": "CCC",
        "company": "CCC Inc.",
        "side": "buy",
        "insider_count": 2,
        "multiple_insiders": True,
        "insiders": ["Ins"],
        "total_insider_shares": 30000.0,
        "current_price": 20.0,
        "fifty_two_week_high": 100.0,
        "discount_pct": 80.0,
        "suggested_quantity": 5000,
        # aggregate_by_issuer orders contributing rows newest-first, ties on
        # accession_no descending.
        "filings": [
            {
                "accession_no": "ccc-2",
                "filing_date": "2026-08-21",
                "transaction_date": "2026-08-20",
                "insider_name": "Ins",
                "shares": 15000.0,
                "price": 1.0,
            },
            {
                "accession_no": "ccc-1",
                "filing_date": "2026-08-21",
                "transaction_date": "2026-08-20",
                "insider_name": "Ins",
                "shares": 15000.0,
                "price": 1.0,
            },
        ],
    }


def test_sold_direction_maps_side_to_sell():
    txns = [
        _txn("XYZ", 10000, "x1", code="S", accession="x-1"),
        _txn("XYZ", 10000, "x2", code="S", accession="x-2"),
    ]
    result = _run(txns, {"XYZ": 10.0}, {"XYZ": 100.0}, min_shares=5000, pct_below_high=70)
    assert result["results"][0]["side"] == "sell"


def test_suggested_quantity_is_the_selected_share_size():
    result = _run(RANKING_TXNS, RANKING_PRICES, RANKING_HIGHS, min_shares=15000, pct_below_high=50)
    assert {r["suggested_quantity"] for r in result["results"]} == {15000}
    # min_shares=15000 also drops BBB's two 5000-share lines.
    assert "BBB" not in {r["ticker"] for r in result["results"]}


def test_pagination_second_page():
    many = []
    prices = {}
    highs = {}
    for i in range(23):
        ticker = f"T{i:02d}"
        many += [
            _txn(ticker, 10000, f"{ticker}-a", accession=f"{ticker}-1"),
            _txn(ticker, 10000, f"{ticker}-b", accession=f"{ticker}-2"),
        ]
        prices[ticker] = 10.0
        highs[ticker] = 100.0

    page1 = _run(many, prices, highs, page=1)
    page2 = _run(many, prices, highs, page=2)
    page3 = _run(many, prices, highs, page=3)

    assert page1["total_count"] == 23
    assert page1["total_pages"] == 3
    assert len(page1["results"]) == PAGE_SIZE
    assert page1["has_next"] is True
    assert len(page2["results"]) == PAGE_SIZE
    assert page3["has_next"] is False
    assert len(page3["results"]) == 3
    # No overlap across pages.
    seen = [r["ticker"] for r in page1["results"] + page2["results"] + page3["results"]]
    assert len(seen) == len(set(seen)) == 23


def test_page_out_of_range_returns_empty_but_valid_metadata():
    result = _run(RANKING_TXNS, RANKING_PRICES, RANKING_HIGHS, page=99)
    assert result["results"] == []
    assert result["total_count"] == 4
    assert result["page"] == 99
    assert result["has_next"] is False


@pytest.mark.parametrize("bad_page, normalized", [(0, 1), (-3, 1), ("abc", 1), (None, 1)])
def test_bad_page_coerces_to_one(bad_page, normalized):
    result = _run(RANKING_TXNS, RANKING_PRICES, RANKING_HIGHS, page=bad_page)
    assert result["page"] == normalized


def test_empty_when_nothing_survives_the_price_filter():
    result = _run(RANKING_TXNS, {t: 999.0 for t in RANKING_PRICES}, RANKING_HIGHS)
    assert result["results"] == []
    assert result["total_count"] == 0
    assert result["total_pages"] == 1


def test_passes_direction_and_months_to_the_source():
    source = _source(RANKING_TXNS)
    run_screen(
        direction="Sold",
        months=3,
        transactions_source=source,
        price_lookup=_lookup(RANKING_PRICES),
        high_lookup=_lookup(RANKING_HIGHS),
        min_shares=5000,
        pct_below_high=50,
    )
    assert source.calls == [("Sold", 3)]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"direction": "Hold"},
        {"months": 9},
        {"min_shares": 12345},
        {"pct_below_high": 55},
    ],
)
def test_out_of_range_parameters_raise_screener_param_error(kwargs):
    from screener_errors import ScreenerParamError

    with pytest.raises(ScreenerParamError):
        _run(RANKING_TXNS, RANKING_PRICES, RANKING_HIGHS, **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [{"direction": "Hold"}, {"months": 9}, {"min_shares": 12345}, {"pct_below_high": 55}],
)
def test_parameters_are_validated_before_the_transaction_source_is_called(kwargs):
    from screener_errors import ScreenerParamError

    source = _source(RANKING_TXNS)
    with pytest.raises(ScreenerParamError):
        run_screen(
            transactions_source=source,
            price_lookup=_lookup(RANKING_PRICES),
            high_lookup=_lookup(RANKING_HIGHS),
            **{"min_shares": 5000, "pct_below_high": 50, **kwargs},
        )
    assert source.calls == []
