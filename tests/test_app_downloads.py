"""Tests for the App Store Downloads analytics tool and report-resolution flow.

All Apple API interaction is mocked via FakeAnalyticsClient - no real network calls.
"""

import asyncio
from pathlib import Path

import pytest

from apple_mcp.analytics_report_source import (
    AnalyticsReportNotReadyError,
    ensure_ongoing_report_request,
    resolve_app_downloads_segment_urls,
)
from apple_mcp.client import ApiError
from apple_mcp.tools import app_downloads as app_downloads_tool

FIXTURES = Path(__file__).parent / "fixtures"


class FakeAnalyticsClient:
    """Fakes the subset of ApiClient used by analytics_report_source / tools.app_downloads."""

    def __init__(
        self,
        *,
        existing_request_id: str | None = None,
        create_response: dict | None = None,
        create_error: ApiError | None = None,
        reports: list[dict] | None = None,
        instances: list[dict] | None = None,
        segments: list[dict] | None = None,
        segment_raw: str = "",
    ):
        self.existing_request_id = existing_request_id
        self.create_response = create_response
        self.create_error = create_error
        self.reports = reports if reports is not None else []
        self.instances = instances if instances is not None else []
        self.segments = segments if segments is not None else []
        self.segment_raw = segment_raw

        self.create_calls: list[tuple[str, str]] = []
        self.list_request_calls: list[str] = []
        self.list_reports_calls: list[tuple[str, str | None]] = []
        self.list_instances_calls: list[tuple[str, str, str | None]] = []
        self.list_segments_calls: list[str] = []
        self.fetch_segment_calls: list[str] = []

    async def list_analytics_report_requests(self, app_id: str) -> dict:
        self.list_request_calls.append(app_id)
        if self.existing_request_id:
            return {
                "data": [
                    {"id": self.existing_request_id, "attributes": {"accessType": "ONGOING"}}
                ]
            }
        return {"data": []}

    async def create_analytics_report_request(self, app_id: str, access_type: str = "ONGOING") -> dict:
        self.create_calls.append((app_id, access_type))
        if self.create_error is not None:
            # After the "conflict", pretend the request now exists for re-list.
            self.existing_request_id = self.existing_request_id or "req-existing"
            raise self.create_error
        return self.create_response or {"data": {"id": "req-new"}}

    async def list_analytics_reports(self, report_request_id: str, name: str | None = None) -> dict:
        self.list_reports_calls.append((report_request_id, name))
        matching = [r for r in self.reports if name is None or r["attributes"]["name"] == name]
        return {"data": matching}

    async def list_report_instances(
        self, report_id: str, granularity: str = "DAILY", processing_date: str | None = None
    ) -> dict:
        self.list_instances_calls.append((report_id, granularity, processing_date))
        matching = [
            i
            for i in self.instances
            if (processing_date is None or i["attributes"]["processingDate"] == processing_date)
        ]
        return {"data": matching}

    async def list_report_segments(self, instance_id: str) -> dict:
        self.list_segments_calls.append(instance_id)
        return {"data": self.segments}

    async def fetch_analytics_segment(self, url: str) -> str:
        self.fetch_segment_calls.append(url)
        return self.segment_raw


def _standard_reports():
    return [
        {"id": "report-standard", "attributes": {"name": "App Store Downloads"}},
        {"id": "report-detailed", "attributes": {"name": "App Store Downloads Detailed"}},
    ]


def _standard_instances(date: str = "2026-04-08"):
    return [{"id": "inst-1", "attributes": {"processingDate": date, "granularity": "DAILY"}}]


def _standard_segments():
    return [{"id": "seg-1", "attributes": {"url": "https://presigned.example.com/segment.gz"}}]


# --- ensure_ongoing_report_request -----------------------------------------------------


def test_ensure_ongoing_report_request_reuses_existing():
    client = FakeAnalyticsClient(existing_request_id="req-1")
    request_id = asyncio.run(ensure_ongoing_report_request(client, "app-1"))

    assert request_id == "req-1"
    assert client.create_calls == []


def test_ensure_ongoing_report_request_creates_when_missing():
    client = FakeAnalyticsClient(create_response={"data": {"id": "req-new"}})
    request_id = asyncio.run(ensure_ongoing_report_request(client, "app-1"))

    assert request_id == "req-new"
    assert client.create_calls == [("app-1", "ONGOING")]


def test_ensure_ongoing_report_request_falls_back_on_409_conflict():
    client = FakeAnalyticsClient(create_error=ApiError(409, "already exists", "/v1/analyticsReportRequests"))
    request_id = asyncio.run(ensure_ongoing_report_request(client, "app-1"))

    # Should recover by re-listing rather than raising the 409 to the caller.
    assert request_id == "req-existing"
    assert client.create_calls == [("app-1", "ONGOING")]


def test_ensure_ongoing_report_request_reraises_non_409_errors():
    client = FakeAnalyticsClient(create_error=ApiError(500, "boom", "/v1/analyticsReportRequests"))
    with pytest.raises(ApiError):
        asyncio.run(ensure_ongoing_report_request(client, "app-1"))


# --- resolve_app_downloads_segment_urls ------------------------------------------------


def test_resolve_app_downloads_segment_urls_happy_path():
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(),
        segments=_standard_segments(),
    )

    urls = asyncio.run(
        resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08", detailed=True)
    )

    assert urls == ["https://presigned.example.com/segment.gz"]
    # Detailed report name was requested
    assert client.list_reports_calls[-1] == ("req-1", "App Store Downloads Detailed")


def test_resolve_app_downloads_segment_urls_uses_standard_name_when_not_detailed():
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(),
        segments=_standard_segments(),
    )

    asyncio.run(resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08", detailed=False))

    assert client.list_reports_calls[-1] == ("req-1", "App Store Downloads")


def test_resolve_app_downloads_segment_urls_raises_when_report_missing():
    client = FakeAnalyticsClient(existing_request_id="req-1", reports=[])

    with pytest.raises(AnalyticsReportNotReadyError):
        asyncio.run(resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08"))


def test_resolve_app_downloads_segment_urls_raises_when_no_matching_instance():
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(date="2026-01-01"),  # different date
        segments=_standard_segments(),
    )

    with pytest.raises(AnalyticsReportNotReadyError, match="T\\+2"):
        asyncio.run(resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08"))


def test_resolve_app_downloads_segment_urls_raises_when_no_segments():
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(),
        segments=[],
    )

    with pytest.raises(AnalyticsReportNotReadyError):
        asyncio.run(resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08"))


# --- tools/app_downloads.py aggregation ------------------------------------------------


def test_get_app_downloads_report_group_by_download_type():
    app_downloads_tool._cache.clear()
    raw = (FIXTURES / "sample_app_downloads.tsv").read_text()
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(),
        segments=_standard_segments(),
        segment_raw=raw,
    )

    result = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client, "app-1", "2026-04-08", group_by="download_type"
        )
    )

    assert result["total_downloads"] == 120 + 15 + 40 + 8
    breakdown_by_key = {item["key"]: item["counts"] for item in result["breakdown"]}
    assert breakdown_by_key["First-Time Download"] == 160
    assert breakdown_by_key["Redownload"] == 15
    assert breakdown_by_key["Auto-Update"] == 8
    # Sorted descending by counts
    assert result["breakdown"][0]["key"] == "First-Time Download"


def test_get_app_downloads_report_group_by_territory():
    app_downloads_tool._cache.clear()
    raw = (FIXTURES / "sample_app_downloads.tsv").read_text()
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(),
        segments=_standard_segments(),
        segment_raw=raw,
    )

    result = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client, "app-1", "2026-04-08", group_by="territory"
        )
    )

    breakdown_by_key = {item["key"]: item["counts"] for item in result["breakdown"]}
    assert breakdown_by_key["US"] == 135
    assert breakdown_by_key["JP"] == 40
    assert breakdown_by_key["GB"] == 8


def test_get_app_downloads_report_caches_parsed_rows_not_urls():
    app_downloads_tool._cache.clear()
    raw = (FIXTURES / "sample_app_downloads.tsv").read_text()
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(),
        segments=_standard_segments(),
        segment_raw=raw,
    )

    asyncio.run(app_downloads_tool.get_app_downloads_report(client, "app-1", "2026-04-08"))
    asyncio.run(app_downloads_tool.get_app_downloads_report(client, "app-1", "2026-04-08"))

    # Second call should be served from cache: no repeated segment resolution/fetch.
    assert len(client.fetch_segment_calls) == 1
    assert len(client.list_segments_calls) == 1


def test_get_app_downloads_report_propagates_not_ready_error():
    app_downloads_tool._cache.clear()
    client = FakeAnalyticsClient(existing_request_id="req-1", reports=[])

    with pytest.raises(AnalyticsReportNotReadyError):
        asyncio.run(app_downloads_tool.get_app_downloads_report(client, "app-1", "2026-04-08"))
