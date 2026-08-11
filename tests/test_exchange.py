"""Tests for exchange rate fetching and the get_exchange_rates tool.

All requests are served by httpx.MockTransport - no real network calls are made.
"""

import asyncio
import datetime

import httpx
import pytest

from apple_mcp import exchange as exchange_module
from apple_mcp.exchange import fetch_historical_rates_to_usd, get_rates_to_usd
from apple_mcp.tools import exchange as exchange_tool


@pytest.fixture(autouse=True)
def _clear_caches():
    exchange_module._rate_cache.clear()
    exchange_module._cache_timestamps.clear()
    exchange_module._historical_rate_cache.clear()
    exchange_module._historical_as_of_cache.clear()
    yield
    exchange_module._rate_cache.clear()
    exchange_module._cache_timestamps.clear()
    exchange_module._historical_rate_cache.clear()
    exchange_module._historical_as_of_cache.clear()


def _mock_httpx_get(monkeypatch, handler):
    """Monkeypatch httpx.AsyncClient (as used inside exchange.py) to route via MockTransport."""

    _real_async_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _real_async_client(*args, **kwargs)

    monkeypatch.setattr(exchange_module.httpx, "AsyncClient", _factory)


def test_fetch_historical_rates_parses_and_inverts(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "amount": 1,
                "base": "USD",
                "date": "2026-04-08",
                "rates": {"EUR": 0.92, "GBP": 0.8},
            },
        )

    _mock_httpx_get(monkeypatch, handler)

    rates, actual_date = asyncio.run(fetch_historical_rates_to_usd("2026-04-08"))

    assert "frankfurter.dev" in captured["url"]
    assert actual_date == "2026-04-08"
    assert rates["USD"] == 1.0
    assert rates["EUR"] == pytest.approx(1 / 0.92)
    assert rates["GBP"] == pytest.approx(1 / 0.8)


def test_fetch_historical_rates_surfaces_actual_returned_date(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        # Requested a weekend date; Frankfurter returns prior business day.
        return httpx.Response(
            200,
            json={"amount": 1, "base": "USD", "date": "2026-04-03", "rates": {"EUR": 0.9}},
        )

    _mock_httpx_get(monkeypatch, handler)

    rates, actual_date = asyncio.run(fetch_historical_rates_to_usd("2026-04-05"))

    assert actual_date == "2026-04-03"
    assert rates["EUR"] == pytest.approx(1 / 0.9)


def test_fetch_historical_rates_raises_on_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    _mock_httpx_get(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(fetch_historical_rates_to_usd("1999-01-01"))


def test_get_rates_to_usd_realtime_inverts_and_includes_usd(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rates": {"EUR": 0.92}})

    _mock_httpx_get(monkeypatch, handler)

    rates = asyncio.run(get_rates_to_usd("2026-08-11"))

    assert rates["USD"] == 1.0
    assert rates["EUR"] == pytest.approx(1 / 0.92)


def test_get_exchange_rates_uses_realtime_path_for_today(monkeypatch):
    class _FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2026, 8, 11, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(exchange_tool.datetime, "datetime", _FakeDatetime)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rates": {"EUR": 0.92}})

    _mock_httpx_get(monkeypatch, handler)

    result = asyncio.run(exchange_tool.get_exchange_rates("2026-08-11"))

    assert result["requested_date"] == "2026-08-11"
    assert result["fx_source"] == "open.er-api.com (realtime)"
    assert "fx_fetched_at" in result
    assert "realtime" in result["disclaimer"].lower() or "current" in result["disclaimer"].lower()
    assert result["rates"]["USD"] == 1.0


def test_get_exchange_rates_uses_historical_path_for_past_date(monkeypatch):
    class _FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2026, 8, 11, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(exchange_tool.datetime, "datetime", _FakeDatetime)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"amount": 1, "base": "USD", "date": "2026-04-08", "rates": {"EUR": 0.92}},
        )

    _mock_httpx_get(monkeypatch, handler)

    result = asyncio.run(exchange_tool.get_exchange_rates("2026-04-08"))

    assert result["requested_date"] == "2026-04-08"
    assert result["fx_source"] == "frankfurter.app (ECB historical reference rates)"
    assert result["fx_as_of"] == "2026-04-08"
    assert "ecb" in result["disclaimer"].lower()
    assert result["rates"]["USD"] == 1.0


def test_get_exchange_rates_currency_filter_returns_single_rate(monkeypatch):
    class _FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2026, 8, 11, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(exchange_tool.datetime, "datetime", _FakeDatetime)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"amount": 1, "base": "USD", "date": "2026-04-08", "rates": {"EUR": 0.92}},
        )

    _mock_httpx_get(monkeypatch, handler)

    result = asyncio.run(exchange_tool.get_exchange_rates("2026-04-08", currency="eur"))

    assert result["currency"] == "EUR"
    assert result["rate"] == pytest.approx(1 / 0.92)
    assert result["usd"] == 1.0
    assert "rates" not in result


def test_get_exchange_rates_unknown_currency_raises(monkeypatch):
    class _FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.datetime(2026, 8, 11, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(exchange_tool.datetime, "datetime", _FakeDatetime)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"amount": 1, "base": "USD", "date": "2026-04-08", "rates": {"EUR": 0.92}},
        )

    _mock_httpx_get(monkeypatch, handler)

    with pytest.raises(ValueError):
        asyncio.run(exchange_tool.get_exchange_rates("2026-04-08", currency="ZZZ"))
