"""Tests for local report source resolution."""

import asyncio
import gzip
from pathlib import Path

import pytest

from apple_mcp.report_source import ReportSourceError, resolve_finance_report_source, resolve_sales_report_source
from apple_mcp.tools import sales as sales_tool

FIXTURES = Path(__file__).parent / "fixtures"


class FakeClient:
    def __init__(self, raw: str = "", vendor_number: str = "12345678"):
        self.raw = raw
        self.vendor_number = vendor_number
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def fetch_gzipped_report(self, path: str, params: dict[str, str]) -> str:
        self.calls.append((path, params))
        return self.raw


def _write_gzip(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(text.encode("utf-8")))


def test_get_sales_report_reads_local_file(monkeypatch, tmp_path):
    sales_tool._cache.clear()
    raw = (FIXTURES / "sample_sales.tsv").read_text()
    _write_gzip(tmp_path / "sales" / "summary" / "daily" / "2026-04-08.tsv.gz", raw)
    monkeypatch.setenv("APP_STORE_REPORT_LOCAL_DIR", str(tmp_path))

    client = FakeClient(raw="should not be used")
    rows = asyncio.run(sales_tool.get_sales_report(client, "2026-04-08", source="local"))

    assert len(rows) == 4
    assert rows[0]["sku"] == "com.example.app"
    assert client.calls == []


def test_get_sales_report_auto_falls_back_to_api(monkeypatch, tmp_path):
    sales_tool._cache.clear()
    raw = (FIXTURES / "sample_sales.tsv").read_text()
    monkeypatch.setenv("APP_STORE_REPORT_LOCAL_DIR", str(tmp_path))

    client = FakeClient(raw=raw)
    rows = asyncio.run(sales_tool.get_sales_report(client, "2026-04-08", source="auto"))

    assert len(rows) == 4
    assert len(client.calls) == 1
    assert client.calls[0][0] == "/v1/salesReports"


def test_get_sales_report_uses_separate_cache_keys_for_local_and_api(monkeypatch, tmp_path):
    sales_tool._cache.clear()
    raw = (FIXTURES / "sample_sales.tsv").read_text()
    header_only = "Provider\tUnits\n"
    _write_gzip(tmp_path / "sales" / "summary" / "daily" / "2026-04-08.tsv.gz", raw)
    monkeypatch.setenv("APP_STORE_REPORT_LOCAL_DIR", str(tmp_path))

    local_client = FakeClient(raw="unused")
    api_client = FakeClient(raw=header_only)

    local_rows = asyncio.run(sales_tool.get_sales_report(local_client, "2026-04-08", source="local"))
    api_rows = asyncio.run(sales_tool.get_sales_report(api_client, "2026-04-08", source="api"))

    assert len(local_rows) == 4
    assert api_rows == []
    assert len(api_client.calls) == 1


def test_get_sales_report_local_requires_local_dir(monkeypatch):
    sales_tool._cache.clear()
    monkeypatch.delenv("APP_STORE_REPORT_LOCAL_DIR", raising=False)

    with pytest.raises(ReportSourceError, match="APP_STORE_REPORT_LOCAL_DIR"):
        asyncio.run(sales_tool.get_sales_report(FakeClient(), "2026-04-08", source="local"))


def test_resolve_finance_report_source_finds_financial_directory_file(monkeypatch, tmp_path):
    report_path = tmp_path / "financial" / "ZZ" / "2026-03.tsv.gz"
    _write_gzip(report_path, "Start Date\tEnd Date\n")
    monkeypatch.setenv("APP_STORE_REPORT_LOCAL_DIR", str(tmp_path))

    location = resolve_finance_report_source(FakeClient(), "2026-03", "ZZ", source="local")

    assert location.source == "local"
    assert location.local_path == report_path.resolve()


def test_resolve_finance_report_source_finds_financial_extended_directory_file(monkeypatch, tmp_path):
    report_path = tmp_path / "financial_extended" / "ZZ" / "2026-03.tsv.gz"
    _write_gzip(report_path, "Start Date\tEnd Date\n")
    monkeypatch.setenv("APP_STORE_REPORT_LOCAL_DIR", str(tmp_path))

    location = resolve_finance_report_source(FakeClient(), "2026-03", "ZZ", source="local")

    assert location.source == "local"
    assert location.local_path == report_path.resolve()


def test_resolve_sales_report_source_finds_subscription_event_directory_file(monkeypatch, tmp_path):
    report_path = tmp_path / "subscriptions_event" / "daily" / "2026-04-08.tsv.gz"
    _write_gzip(report_path, "Event Date\tEvent\n")
    monkeypatch.setenv("APP_STORE_REPORT_LOCAL_DIR", str(tmp_path))

    location = resolve_sales_report_source(
        FakeClient(),
        "2026-04-08",
        report_type="SUBSCRIPTION_EVENT",
        report_sub_type="SUMMARY",
        date_type="DAILY",
        source="local",
        version="1_3",
    )

    assert location.source == "local"
    assert location.local_path == report_path.resolve()
