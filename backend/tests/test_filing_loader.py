"""Shared parallel filing loader (used by insider_data and form4_ingest.edgar)."""

from unittest.mock import MagicMock, patch

from filing_loader import load_filings


def test_maps_loader_over_items_in_input_order():
    assert load_filings([1, 2, 3], lambda n: n * 10) == [10, 20, 30]


def test_falls_back_to_sequential_when_the_pool_cannot_start():
    # CloudLinux CageFS hosts reject even one extra OS thread with a plain
    # RuntimeError -- the batch must still complete, sequentially.
    calls = []

    def loader(item):
        calls.append(item)
        return item

    with patch("filing_loader.ThreadPoolExecutor") as executor_cls:
        executor = MagicMock()
        executor.map.side_effect = RuntimeError("can't start new thread")
        executor_cls.return_value = executor

        result = load_filings(["a", "b", "c"], loader)

    assert result == ["a", "b", "c"]
    assert calls == ["a", "b", "c"]  # ran once each, in order


def test_passes_max_workers_through():
    with patch("filing_loader.ThreadPoolExecutor") as executor_cls:
        executor_cls.return_value.map.return_value = []
        load_filings([], lambda x: x, max_workers=3)
    executor_cls.assert_called_once_with(max_workers=3)
