import pytest

from screener_pricing import ALLOWED_PCT_BELOW_HIGH, enrich_and_filter


def _candidate(ticker, **extra):
    return {"ticker": ticker, "total_shares": 10000, "multiple_insiders": False, **extra}


def _lookup(mapping):
    return lambda tickers: {t: mapping[t] for t in tickers if t in mapping}


def _run(candidates, pct, prices, highs):
    return enrich_and_filter(
        candidates, pct, price_lookup=_lookup(prices), high_lookup=_lookup(highs)
    )


def test_keeps_a_ticker_trading_far_enough_below_its_high():
    # N=70 -> ceiling = 0.30 * 100 = 30. Price 25 <= 30 -> kept.
    kept = _run([_candidate("AAPL")], 70, {"AAPL": 25.0}, {"AAPL": 100.0})

    assert len(kept) == 1
    row = kept[0]
    assert row["current_price"] == 25.0
    assert row["fifty_two_week_high"] == 100.0
    assert row["price_ceiling"] == pytest.approx(30.0)
    assert row["discount_to_52w_high"] == pytest.approx(0.75)


def test_drops_a_ticker_not_far_enough_below_its_high():
    # N=70 -> ceiling 30. Price 40 > 30 -> dropped.
    assert _run([_candidate("AAPL")], 70, {"AAPL": 40.0}, {"AAPL": 100.0}) == []


def test_filter_boundary_is_inclusive():
    # Price exactly at the ceiling is kept.
    kept = _run([_candidate("AAPL")], 70, {"AAPL": 30.0}, {"AAPL": 100.0})
    assert len(kept) == 1


@pytest.mark.parametrize(
    "pct, price, kept",
    [
        (50, 50.0, True),
        (50, 50.01, False),
        (60, 40.0, True),
        (80, 20.0, True),
        (80, 20.01, False),
        (90, 10.0, True),
        (90, 10.01, False),
    ],
)
def test_filter_math_across_percentages(pct, price, kept):
    result = _run([_candidate("AAPL")], pct, {"AAPL": price}, {"AAPL": 100.0})
    assert (len(result) == 1) is kept


def test_pct_100_yields_no_matches():
    # (1 - 100/100) * high = 0; nothing trades at or below $0.
    assert _run([_candidate("AAPL")], 100, {"AAPL": 0.01}, {"AAPL": 100.0}) == []


def test_ticker_without_a_current_price_is_dropped():
    assert _run([_candidate("AAPL")], 70, {}, {"AAPL": 100.0}) == []


def test_ticker_without_a_52_week_high_is_dropped():
    assert _run([_candidate("AAPL")], 70, {"AAPL": 25.0}, {}) == []


def test_ticker_with_non_positive_high_is_dropped():
    assert _run([_candidate("AAPL")], 70, {"AAPL": 25.0}, {"AAPL": 0.0}) == []


def test_one_unpriceable_ticker_does_not_sink_the_others():
    candidates = [_candidate("AAPL"), _candidate("MSFT"), _candidate("TSLA")]
    kept = _run(
        candidates,
        70,
        {"AAPL": 25.0, "TSLA": 90.0},  # MSFT missing price; TSLA above ceiling
        {"AAPL": 100.0, "MSFT": 100.0, "TSLA": 100.0},
    )
    assert [c["ticker"] for c in kept] == ["AAPL"]


def test_candidate_fields_are_preserved():
    kept = _run(
        [_candidate("AAPL", multiple_insiders=True, insider_count=3)],
        70,
        {"AAPL": 25.0},
        {"AAPL": 100.0},
    )
    assert kept[0]["multiple_insiders"] is True
    assert kept[0]["insider_count"] == 3


def test_empty_candidates_returns_empty():
    assert enrich_and_filter([], 70) == []


def test_lookups_receive_the_candidate_tickers():
    seen = {}

    def price_lookup(tickers):
        seen["prices"] = list(tickers)
        return {t: 1.0 for t in tickers}

    def high_lookup(tickers):
        seen["highs"] = list(tickers)
        return {t: 100.0 for t in tickers}

    enrich_and_filter(
        [_candidate("AAPL"), _candidate("MSFT")], 70,
        price_lookup=price_lookup, high_lookup=high_lookup,
    )
    assert seen["prices"] == ["AAPL", "MSFT"]
    assert seen["highs"] == ["AAPL", "MSFT"]


@pytest.mark.parametrize("bad", [0, 55, 75, 110, -70, "seventy", None])
def test_invalid_pct_raises_value_error(bad):
    with pytest.raises(ValueError):
        enrich_and_filter([_candidate("AAPL")], bad)


@pytest.mark.parametrize("pct", ALLOWED_PCT_BELOW_HIGH)
def test_all_ui_percentages_are_accepted(pct):
    _run([_candidate("AAPL")], pct, {"AAPL": 1.0}, {"AAPL": 100.0})
