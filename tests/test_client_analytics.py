"""Tests for ApiClient's Analytics Reports API methods.

All requests are served by httpx.MockTransport - no real network calls are made.
"""

import asyncio
import gzip
import json

import httpx
import pytest

from apple_mcp.client import ApiClient, ApiError


def _make_client(handler) -> ApiClient:
    client = ApiClient(
        issuer_id="issuer",
        key_id="key",
        private_key_path="/nonexistent.p8",
        vendor_number="12345678",
    )
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=60)
    # Bypass real JWT generation (which would need a private key file on disk).
    client._auth_header = lambda: "Bearer fake-token"
    return client


def test_post_json_sends_body_and_auth_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "req-1"}})

    client = _make_client(handler)
    result = asyncio.run(client.post_json("/v1/analyticsReportRequests", {"data": {"type": "x"}}))

    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer fake-token"
    assert captured["body"] == {"data": {"type": "x"}}
    assert result == {"data": {"id": "req-1"}}


def test_post_json_raises_api_error_on_4xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    client = _make_client(handler)
    with pytest.raises(ApiError) as exc_info:
        asyncio.run(client.post_json("/v1/analyticsReportRequests", {}))
    assert exc_info.value.status_code == 403


def test_create_analytics_report_request_body_shape():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "req-1"}})

    client = _make_client(handler)
    asyncio.run(client.create_analytics_report_request("999", access_type="ONGOING"))

    body = captured["body"]
    assert body["data"]["type"] == "analyticsReportRequests"
    assert body["data"]["attributes"]["accessType"] == "ONGOING"
    assert body["data"]["relationships"]["app"]["data"] == {"type": "apps", "id": "999"}


def test_fetch_analytics_segment_does_not_send_authorization_header():
    captured: dict = {}
    raw = "Date\tCounts\n2026-04-08\t10\n"
    compressed = gzip.compress(raw.encode("utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, content=compressed)

    client = _make_client(handler)
    result = asyncio.run(client.fetch_analytics_segment("https://presigned.example.com/segment.gz"))

    assert result == raw
    assert "authorization" not in captured["headers"]


def test_fetch_analytics_segment_raises_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = _make_client(handler)
    with pytest.raises(ApiError):
        asyncio.run(client.fetch_analytics_segment("https://presigned.example.com/segment.gz"))


def test_list_report_instances_handles_single_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "inst-1", "attributes": {"processingDate": "2026-04-08"}}]},
        )

    client = _make_client(handler)
    result = asyncio.run(client.list_report_instances("report-1", granularity="DAILY", processing_date="2026-04-08"))

    assert len(result["data"]) == 1
    assert result["data"][0]["id"] == "inst-1"


def test_list_report_instances_follows_next_page_links():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "page2" not in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "inst-1"}],
                    "links": {"next": "https://api.appstoreconnect.apple.com/v1/analyticsReports/report-1/instances?page2=1"},
                },
            )
        return httpx.Response(200, json={"data": [{"id": "inst-2"}], "links": {}})

    client = _make_client(handler)
    result = asyncio.run(client.list_report_instances("report-1", granularity="DAILY"))

    assert len(calls) == 2
    assert [item["id"] for item in result["data"]] == ["inst-1", "inst-2"]


def test_list_analytics_reports_passes_name_filter():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": []})

    client = _make_client(handler)
    asyncio.run(client.list_analytics_reports("req-1", name="App Store Downloads"))

    assert captured["params"]["filter[name]"] == "App Store Downloads"


def test_list_report_segments_returns_data():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "seg-1", "attributes": {"url": "https://presigned.example.com/a.gz"}}]},
        )

    client = _make_client(handler)
    result = asyncio.run(client.list_report_segments("inst-1"))

    assert result["data"][0]["attributes"]["url"] == "https://presigned.example.com/a.gz"
