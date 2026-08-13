"""Tests for the App Store Downloads analytics tool and report-resolution flow.

All Apple API interaction is mocked via FakeAnalyticsClient - no real network calls.
"""

import asyncio
from pathlib import Path

import pytest

from apple_mcp.analytics_report_source import (
    AnalyticsReportNotReadyError,
    ensure_ongoing_report_request,
    ensure_report_request,
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
        existing_request_ids: dict[str, str] | None = None,
        create_response: dict | None = None,
        create_error: ApiError | None = None,
        reports: list[dict] | None = None,
        instances: list[dict] | None = None,
        segments: list[dict] | None = None,
        segment_raw: str = "",
    ):
        # existing_request_id is a shorthand for an ONGOING request id; use
        # existing_request_ids ({access_type: id}) to cover multiple access types.
        self.existing_request_ids: dict[str, str] = dict(existing_request_ids or {})
        if existing_request_id:
            self.existing_request_ids.setdefault("ONGOING", existing_request_id)
        self.create_response = create_response
        self.create_error = create_error
        self.reports = reports if reports is not None else []
        self.instances = instances if instances is not None else []
        self.segments = segments if segments is not None else []
        self.segment_raw = segment_raw

        self.create_calls: list[tuple[str, str]] = []
        self.list_request_calls: list[tuple[str, str]] = []
        self.list_reports_calls: list[tuple[str, str | None]] = []
        self.list_instances_calls: list[tuple[str, str, str | None]] = []
        self.list_segments_calls: list[str] = []
        self.fetch_segment_calls: list[str] = []

    @property
    def existing_request_id(self) -> str | None:
        return self.existing_request_ids.get("ONGOING")

    async def list_analytics_report_requests(self, app_id: str, access_type: str = "ONGOING") -> dict:
        self.list_request_calls.append((app_id, access_type))
        existing_id = self.existing_request_ids.get(access_type)
        if existing_id:
            return {"data": [{"id": existing_id, "attributes": {"accessType": access_type}}]}
        return {"data": []}

    async def create_analytics_report_request(self, app_id: str, access_type: str = "ONGOING") -> dict:
        self.create_calls.append((app_id, access_type))
        if self.create_error is not None:
            # After the "conflict", pretend the request now exists for re-list.
            self.existing_request_ids.setdefault(access_type, "req-existing")
            raise self.create_error
        return self.create_response or {"data": {"id": "req-new"}}

    async def list_analytics_reports(self, report_request_id: str, name: str | None = None) -> dict:
        self.list_reports_calls.append((report_request_id, name))
        return {"data": self.reports}

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
        {"id": "report-standard", "attributes": {"name": "App Downloads Standard"}},
        {"id": "report-detailed", "attributes": {"name": "App Downloads Detailed"}},
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


# --- ensure_report_request (ONE_TIME_SNAPSHOT) ------------------------------------------


def test_ensure_report_request_creates_one_time_snapshot_when_missing():
    client = FakeAnalyticsClient(create_response={"data": {"id": "snap-new"}})
    request_id = asyncio.run(ensure_report_request(client, "app-1", access_type="ONE_TIME_SNAPSHOT"))

    assert request_id == "snap-new"
    assert client.create_calls == [("app-1", "ONE_TIME_SNAPSHOT")]
    assert client.list_request_calls == [("app-1", "ONE_TIME_SNAPSHOT")]


def test_ensure_report_request_reuses_existing_one_time_snapshot():
    client = FakeAnalyticsClient(existing_request_ids={"ONE_TIME_SNAPSHOT": "snap-1"})
    request_id = asyncio.run(ensure_report_request(client, "app-1", access_type="ONE_TIME_SNAPSHOT"))

    assert request_id == "snap-1"
    assert client.create_calls == []


def test_ensure_report_request_falls_back_on_409_for_one_time_snapshot():
    client = FakeAnalyticsClient(create_error=ApiError(409, "already exists", "/v1/analyticsReportRequests"))
    request_id = asyncio.run(ensure_report_request(client, "app-1", access_type="ONE_TIME_SNAPSHOT"))

    assert request_id == "req-existing"
    assert client.create_calls == [("app-1", "ONE_TIME_SNAPSHOT")]


def test_ensure_report_request_ongoing_and_snapshot_are_independent():
    # An existing ONGOING request must not satisfy a ONE_TIME_SNAPSHOT lookup, and vice versa.
    client = FakeAnalyticsClient(
        existing_request_ids={"ONGOING": "ongoing-1"},
        create_response={"data": {"id": "snap-new"}},
    )

    snapshot_id = asyncio.run(ensure_report_request(client, "app-1", access_type="ONE_TIME_SNAPSHOT"))
    ongoing_id = asyncio.run(ensure_report_request(client, "app-1", access_type="ONGOING"))

    assert snapshot_id == "snap-new"
    assert ongoing_id == "ongoing-1"
    assert client.create_calls == [("app-1", "ONE_TIME_SNAPSHOT")]


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


def test_resolve_app_downloads_segment_urls_uses_standard_name_when_not_detailed():
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(),
        segments=_standard_segments(),
    )

    urls = asyncio.run(
        resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08", detailed=False)
    )

    assert urls == ["https://presigned.example.com/segment.gz"]


def test_resolve_app_downloads_segment_urls_raises_when_report_missing():
    client = FakeAnalyticsClient(existing_request_id="req-1", reports=[])

    with pytest.raises(AnalyticsReportNotReadyError):
        asyncio.run(resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08"))


def test_resolve_app_downloads_segment_urls_matches_name_case_insensitively():
    # Apple's exact `attributes.name` casing/wording isn't reliably documented,
    # so matching must not depend on an exact-string guess.
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=[
            {"id": "report-standard", "attributes": {"name": "app downloads standard"}},
            {"id": "report-detailed", "attributes": {"name": "App Downloads - Detailed"}},
        ],
        instances=_standard_instances(),
        segments=_standard_segments(),
    )

    urls = asyncio.run(
        resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08", detailed=False)
    )
    assert urls == ["https://presigned.example.com/segment.gz"]

    detailed_urls = asyncio.run(
        resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08", detailed=True)
    )
    assert detailed_urls == ["https://presigned.example.com/segment.gz"]


def test_resolve_app_downloads_segment_urls_raises_when_no_matching_instance():
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(date="2026-01-01"),  # different date
        segments=_standard_segments(),
    )

    with pytest.raises(AnalyticsReportNotReadyError, match="T\\+2"):
        asyncio.run(resolve_app_downloads_segment_urls(client, "app-1", "2026-04-08"))


def test_resolve_app_downloads_segment_urls_uses_one_time_snapshot_request():
    client = FakeAnalyticsClient(
        existing_request_ids={"ONE_TIME_SNAPSHOT": "snap-1"},
        reports=_standard_reports(),
        instances=_standard_instances(date="2026-07-15"),
        segments=_standard_segments(),
    )

    urls = asyncio.run(
        resolve_app_downloads_segment_urls(
            client, "app-1", "2026-07-15", detailed=True, access_type="ONE_TIME_SNAPSHOT"
        )
    )

    assert urls == ["https://presigned.example.com/segment.gz"]
    assert client.list_request_calls == [("app-1", "ONE_TIME_SNAPSHOT")]
    # Must not touch/require an ONGOING request when access_type is ONE_TIME_SNAPSHOT.
    assert client.existing_request_id is None


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


def test_get_app_downloads_report_surfaces_instance_metadata():
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
        app_downloads_tool.get_app_downloads_report(client, "app-1", "2026-04-08")
    )

    assert result["processing_date"] == "2026-04-08"
    assert result["instance_id"] == "inst-1"
    assert result["distinct_raw_dates_before_filter"] == ["2026-04-08"]
    assert result["rows_before_filter"] == 4
    assert result["rows_after_filter"] == 4
    assert result["breakdown_sum_matches_total"] is True


# --- business_date filtering ------------------------------------------------------------


_CROSS_DATE_TSV = (
    "Date\tApp Name\tApp Apple Identifier\tDownload Type\tApp Version\tDevice\t"
    "Platform Version\tSource Type\tSource Info\tCampaign\tPage Type\tPage Title\t"
    "Pre-Order\tTerritory\tCounts\n"
    "2026-08-05\tMy App\t123456789\tFirst-Time Download\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tUS\t100\n"
    "2026-08-06\tMy App\t123456789\tFirst-Time Download\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tUS\t200\n"
    "2026-08-07\tMy App\t123456789\tFirst-Time Download\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tUS\t30\n"
    "2026-08-07\tMy App\t123456789\tRedownload\t1.0\tiPad\t17.4\t"
    "App Store Browse\t\t\tProduct Page\t\tfalse\tJP\t8\n"
)


def test_get_app_downloads_report_business_date_filters_before_aggregation():
    app_downloads_tool._cache.clear()
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(date="2026-08-07"),
        segments=_standard_segments(),
        segment_raw=_CROSS_DATE_TSV,
    )

    result = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client, "app-1", "2026-08-07", group_by="territory", business_date="2026-08-07"
        )
    )

    # Only the two 2026-08-07 rows (30 + 8) should count, not the cross-day total (338).
    assert result["total_downloads"] == 38
    assert result["business_date"] == "2026-08-07"
    assert result["processing_date"] == "2026-08-07"
    assert result["rows_before_filter"] == 4
    assert result["rows_after_filter"] == 2
    assert sorted(result["distinct_raw_dates_before_filter"]) == [
        "2026-08-05",
        "2026-08-06",
        "2026-08-07",
    ]
    breakdown_by_key = {item["key"]: item["counts"] for item in result["breakdown"]}
    assert breakdown_by_key == {"US": 30, "JP": 8}
    assert result["breakdown_sum_matches_total"] is True
    assert "natural_empty" not in result


def test_get_app_downloads_report_business_date_natural_empty_when_no_rows_match():
    app_downloads_tool._cache.clear()
    client = FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(date="2026-08-07"),
        segments=_standard_segments(),
        segment_raw=_CROSS_DATE_TSV,
    )

    result = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client, "app-1", "2026-08-07", business_date="2026-08-09"
        )
    )

    assert result["total_downloads"] == 0
    assert result["rows_after_filter"] == 0
    assert result["natural_empty"] is True
    assert "2026-08-09" in result["note"]


# --- download_type filtering -------------------------------------------------------------


_TYPE_ISOLATION_TSV = (
    "Date\tApp Name\tApp Apple Identifier\tDownload Type\tApp Version\tDevice\t"
    "Platform Version\tSource Type\tSource Info\tCampaign\tPage Type\tPage Title\t"
    "Pre-Order\tTerritory\tCounts\n"
    "2026-07-23\tMy App\t123456789\tFirst-Time Download\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tUS\t150\n"
    "2026-07-23\tMy App\t123456789\tFirst-Time Download\t1.0\tiPad\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tRU\t12\n"
    "2026-07-23\tMy App\t123456789\tFirst-Time Download\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tGB\t9\n"
    "2026-07-23\tMy App\t123456789\tRedownload\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tUS\t5\n"
    "2026-07-23\tMy App\t123456789\tRestore\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tUS\t10\n"
    "2026-07-23\tMy App\t123456789\tAuto-Update\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tUS\t293\n"
    "2026-07-24\tMy App\t123456789\tFirst-Time Download\t1.0\tiPhone\t17.4\t"
    "App Store Search\t\t\tProduct Page\t\tfalse\tUS\t999\n"
)


def _type_isolation_client():
    return FakeAnalyticsClient(
        existing_request_id="req-1",
        reports=_standard_reports(),
        instances=_standard_instances(date="2026-08-07"),
        segments=_standard_segments(),
        segment_raw=_TYPE_ISOLATION_TSV,
    )


def test_get_app_downloads_report_download_type_filters_before_aggregation():
    app_downloads_tool._cache.clear()
    client = _type_isolation_client()

    result = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client,
            "app-1",
            "2026-08-07",
            group_by="territory",
            business_date="2026-07-23",
            download_type="First-time download",
        )
    )

    assert result["total_downloads"] == 171
    breakdown_by_key = {item["key"]: item["counts"] for item in result["breakdown"]}
    assert breakdown_by_key == {"US": 150, "RU": 12, "GB": 9}
    assert result["breakdown_sum_matches_total"] is True
    assert result["download_type"] == "First-time download"
    assert result["business_date"] == "2026-07-23"
    assert result["rows_before_filter"] == 7
    assert result["rows_after_business_date_filter"] == 6
    assert result["rows_after_download_type_filter"] == 3
    assert "natural_empty" not in result
    assert "app_id" in result
    assert "report_id" in result
    assert "source_segment_sha256" in result


def test_get_app_downloads_report_download_type_redownload():
    app_downloads_tool._cache.clear()
    client = _type_isolation_client()

    result = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client,
            "app-1",
            "2026-08-07",
            group_by="territory",
            business_date="2026-07-23",
            download_type="Redownload",
        )
    )

    assert result["total_downloads"] == 5
    breakdown_by_key = {item["key"]: item["counts"] for item in result["breakdown"]}
    assert breakdown_by_key == {"US": 5}
    assert result["breakdown_sum_matches_total"] is True


def test_get_app_downloads_report_download_type_isolation():
    app_downloads_tool._cache.clear()
    client = _type_isolation_client()

    first_time = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client,
            "app-1",
            "2026-08-07",
            business_date="2026-07-23",
            download_type="First-time download",
        )
    )
    keys = {item["key"] for item in first_time["breakdown"]}
    assert keys == {"First-Time Download"} or keys == set()

    # The grouping key when group_by defaults to download_type must only ever
    # surface the requested type - no cross-contamination from other types.
    redownload = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client,
            "app-1",
            "2026-08-07",
            business_date="2026-07-23",
            download_type="Redownload",
        )
    )
    redownload_keys = {item["key"] for item in redownload["breakdown"]}
    assert "First-Time Download" not in redownload_keys
    assert "Restore" not in redownload_keys
    assert "Auto-Update" not in redownload_keys


def test_get_app_downloads_report_invalid_download_type_raises():
    app_downloads_tool._cache.clear()
    client = _type_isolation_client()

    with pytest.raises(app_downloads_tool.InvalidDownloadTypeError, match="INVALID_DOWNLOAD_TYPE"):
        asyncio.run(
            app_downloads_tool.get_app_downloads_report(
                client, "app-1", "2026-08-07", download_type="Not A Real Type"
            )
        )


def test_get_app_downloads_report_download_type_natural_empty():
    app_downloads_tool._cache.clear()
    client = _type_isolation_client()

    result = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client,
            "app-1",
            "2026-08-07",
            business_date="2026-07-25",
            download_type="Restore",
        )
    )

    assert result["total_downloads"] == 0
    assert result["breakdown"] == []
    assert result["natural_empty"] is True
    assert result["rows_after_download_type_filter"] == 0
    assert result["breakdown_sum_matches_total"] is True


def test_get_app_downloads_report_download_type_omitted_is_backward_compatible():
    app_downloads_tool._cache.clear()
    client = _type_isolation_client()

    result = asyncio.run(
        app_downloads_tool.get_app_downloads_report(
            client, "app-1", "2026-08-07", business_date="2026-07-23"
        )
    )

    assert result["total_downloads"] == 150 + 12 + 9 + 5 + 10 + 293
    assert "download_type" not in result
    assert result["rows_after_business_date_filter"] == result["rows_after_download_type_filter"]
