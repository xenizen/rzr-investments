"""The SCREENER_USE_DB dispatch shim (SCRUM-46)."""

import sys
import types

import pytest

import screener_source


@pytest.fixture
def stub_sources(monkeypatch):
    calls = []
    monkeypatch.setattr(
        screener_source.screener_repo, "get_insider_transactions",
        lambda direction, *, months: calls.append(("db", direction, months)) or [],
    )
    fake = types.ModuleType("screener_data")
    fake.get_insider_transactions = lambda direction: calls.append(("edgar", direction)) or []
    monkeypatch.setitem(sys.modules, "screener_data", fake)
    return calls


def test_defaults_to_the_db(monkeypatch, stub_sources):
    monkeypatch.delenv("SCREENER_USE_DB", raising=False)
    screener_source.get_insider_transactions("Purchase", months=3)
    assert stub_sources == [("db", "Purchase", 3)]


def test_flag_off_falls_back_to_live_edgar(monkeypatch, stub_sources):
    monkeypatch.setenv("SCREENER_USE_DB", "0")
    screener_source.get_insider_transactions("Sold", months=3)
    assert stub_sources == [("edgar", "Sold")]  # months not passed to the legacy path
