import pytest

from screener import ALLOWED_SHARE_SIZES, aggregate_by_issuer


def _txn(
    *,
    ticker="AAPL",
    shares=10000.0,
    insider_cik="0001111111",
    insider_name="Jane Doe",
    code="P",
    tdate="2026-08-24",
    accession="a-1",
    issuer_cik="0000320193",
    issuer_name="Apple Inc.",
    price=50.0,
    filing_date="2026-08-25",
):
    return {
        "issuer_ticker": ticker,
        "issuer_cik": issuer_cik,
        "issuer_name": issuer_name,
        "insider_name": insider_name,
        "insider_cik": insider_cik,
        "transaction_code": code,
        "transaction_date": tdate,
        "shares": shares,
        "price": price,
        "filing_date": filing_date,
        "accession_no": accession,
    }


def _only(candidates):
    assert len(candidates) == 1
    return candidates[0]


def test_transactions_below_the_threshold_do_not_produce_a_candidate():
    assert aggregate_by_issuer([_txn(shares=4999)], 5000) == []


def test_threshold_is_inclusive():
    candidate = _only(aggregate_by_issuer([_txn(shares=5000)], 5000))
    assert candidate["total_shares"] == 5000


def test_sub_threshold_rows_are_excluded_from_the_aggregate_total():
    txns = [
        _txn(shares=10000, insider_cik="c1", accession="a-1"),
        _txn(shares=3000, insider_cik="c2", accession="a-2"),  # dropped
    ]
    candidate = _only(aggregate_by_issuer(txns, 5000))
    assert candidate["total_shares"] == 10000
    assert candidate["insider_count"] == 1
    assert candidate["transactions"] == [txns[0]]


def test_aggregates_multiple_qualifying_transactions_for_one_issuer():
    txns = [
        _txn(shares=10000, insider_cik="c1", accession="a-1"),
        _txn(shares=15000, insider_cik="c1", accession="a-2"),
    ]
    candidate = _only(aggregate_by_issuer(txns, 5000))
    assert candidate["total_shares"] == 25000
    assert candidate["ticker"] == "AAPL"


def test_distinct_insiders_counted_by_cik_not_name():
    # Same person (CIK), name recorded two different ways -> one insider.
    txns = [
        _txn(insider_cik="c1", insider_name="Jane Doe", accession="a-1"),
        _txn(insider_cik="c1", insider_name="DOE JANE", accession="a-2"),
    ]
    candidate = _only(aggregate_by_issuer(txns, 5000))
    assert candidate["insider_count"] == 1
    assert candidate["multiple_insiders"] is False


def test_same_name_different_cik_counts_as_two_insiders():
    txns = [
        _txn(insider_cik="c1", insider_name="John Smith", accession="a-1"),
        _txn(insider_cik="c2", insider_name="John Smith", accession="a-2"),
    ]
    candidate = _only(aggregate_by_issuer(txns, 5000))
    assert candidate["insider_count"] == 2
    assert candidate["multiple_insiders"] is True


def test_multiple_insiders_flag_true_for_two_distinct_ciks():
    txns = [
        _txn(insider_cik="c1", insider_name="Jane Doe", shares=10000, accession="a-1"),
        _txn(insider_cik="c2", insider_name="John Smith", shares=20000, accession="a-2"),
        _txn(insider_cik="c3", insider_name="Amy Lin", shares=6000, accession="a-3"),
    ]
    candidate = _only(aggregate_by_issuer(txns, 5000))
    assert candidate["insider_count"] == 3
    assert candidate["multiple_insiders"] is True
    assert candidate["total_shares"] == 36000
    assert candidate["insiders"] == ["Amy Lin", "Jane Doe", "John Smith"]


def test_missing_cik_falls_back_to_name_for_dedup():
    same_name = [
        _txn(insider_cik="", insider_name="Pat Roe", accession="a-1"),
        _txn(insider_cik="", insider_name="Pat Roe", accession="a-2"),
    ]
    assert _only(aggregate_by_issuer(same_name, 5000))["insider_count"] == 1

    diff_name = [
        _txn(insider_cik="", insider_name="Pat Roe", accession="a-1"),
        _txn(insider_cik="", insider_name="Sam Loe", accession="a-2"),
    ]
    assert _only(aggregate_by_issuer(diff_name, 5000))["insider_count"] == 2


def test_groups_are_split_by_ticker_and_sorted():
    txns = [
        _txn(ticker="MSFT", insider_cik="c1", accession="a-1"),
        _txn(ticker="AAPL", insider_cik="c2", accession="a-2"),
        _txn(ticker="MSFT", insider_cik="c3", accession="a-3"),
    ]
    candidates = aggregate_by_issuer(txns, 5000)
    assert [c["ticker"] for c in candidates] == ["AAPL", "MSFT"]
    assert candidates[0]["insider_count"] == 1
    assert candidates[1]["insider_count"] == 2


def test_contributing_transactions_are_ordered_newest_first():
    txns = [
        _txn(tdate="2026-08-20", accession="a-1", insider_cik="c1"),
        _txn(tdate="2026-08-24", accession="a-2", insider_cik="c2"),
        _txn(tdate="2026-08-22", accession="a-3", insider_cik="c3"),
    ]
    candidate = _only(aggregate_by_issuer(txns, 5000))
    assert [t["transaction_date"] for t in candidate["transactions"]] == [
        "2026-08-24",
        "2026-08-22",
        "2026-08-20",
    ]


def test_carries_issuer_metadata_and_transaction_code():
    candidate = _only(
        aggregate_by_issuer([_txn(code="S", issuer_cik="0000320193", issuer_name="Apple Inc.")], 5000)
    )
    assert candidate["transaction_code"] == "S"
    assert candidate["issuer_cik"] == "0000320193"
    assert candidate["issuer_name"] == "Apple Inc."


def test_rows_without_a_ticker_are_skipped():
    assert aggregate_by_issuer([_txn(ticker="")], 5000) == []


def test_empty_input_returns_empty_list():
    assert aggregate_by_issuer([], 10000) == []


@pytest.mark.parametrize("bad", [0, 100, 7500, 25000, -5000, "big", None])
def test_invalid_min_shares_raises_value_error(bad):
    with pytest.raises(ValueError):
        aggregate_by_issuer([_txn()], bad)


@pytest.mark.parametrize("size", ALLOWED_SHARE_SIZES)
def test_all_ui_share_sizes_are_accepted(size):
    aggregate_by_issuer([_txn(shares=size)], size)
