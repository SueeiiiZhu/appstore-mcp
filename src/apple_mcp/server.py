"""MCP server definition with tool registration."""

import json
import os
import sys
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP

from .analytics_report_source import (
    AnalyticsReportNotReadyError,
    ensure_report_request,
    resolve_app_downloads_segment_urls,
)
from .client import ApiClient, ApiError
from .parsers import parse_app_downloads_report, parse_tsv
from .report_source import ReportSourceError, list_local_reports as list_local_reports_from_archive
from .tools.app_downloads import get_app_downloads_report
from .tools.finance import get_finance_report
from .tools.installs import get_install_stats
from .tools.revenue import get_revenue_summary
from .tools.reviews import get_customer_reviews
from .tools.sales import get_sales_report
from .tools.subscriptions import get_subscription_report

mcp = FastMCP("apple-appstore-reports")

_client: ApiClient | None = None
_local_only_client: ApiClient | None = None


def _get_client(require_auth: bool = True) -> ApiClient:
    global _client, _local_only_client

    if require_auth:
        if _client is None:
            _client = ApiClient(
                issuer_id=_require_env("APP_STORE_CONNECT_ISSUER_ID"),
                key_id=_require_env("APP_STORE_CONNECT_KEY_ID"),
                private_key_path=_require_env("APP_STORE_CONNECT_PRIVATE_KEY_PATH"),
                vendor_number=_require_env("APP_STORE_CONNECT_VENDOR_NUMBER"),
            )
        return _client

    if _local_only_client is None:
        _local_only_client = ApiClient(
            issuer_id=os.environ.get("APP_STORE_CONNECT_ISSUER_ID", ""),
            key_id=os.environ.get("APP_STORE_CONNECT_KEY_ID", ""),
            private_key_path=os.environ.get("APP_STORE_CONNECT_PRIVATE_KEY_PATH", ""),
            vendor_number=os.environ.get("APP_STORE_CONNECT_VENDOR_NUMBER", ""),
        )
    return _local_only_client


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _result(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool(name="get_revenue_summary")
async def get_revenue_summary_tool(
    date: Annotated[str, "Report date in YYYY-MM-DD format (e.g. 2026-04-08)"],
    group_by: Annotated[
        Literal["app", "country", "device"],
        "Dimension to group revenue by",
    ] = "app",
    source: Annotated[
        Literal["auto", "api", "local"],
        "Data source: auto prefers local archive, api forces Apple API, local requires APP_STORE_REPORT_LOCAL_DIR",
    ] = "auto",
) -> str:
    """Get daily revenue summary with aggregation. Returns total proceeds and breakdown by app, country, or device."""
    try:
        result = await get_revenue_summary(_get_client(require_auth=source != "local"), date, group_by, source)
        return _result(result)
    except ApiError as e:
        return e.to_user_message()
    except ReportSourceError as e:
        return str(e)


@mcp.tool(name="get_install_stats")
async def get_install_stats_tool(
    date: Annotated[str, "Report date in YYYY-MM-DD format (e.g. 2026-04-08)"],
    group_by: Annotated[
        Literal["app", "country", "device"],
        "Dimension to group installs by",
    ] = "app",
    source: Annotated[
        Literal["auto", "api", "local"],
        "Data source: auto prefers local archive, api forces Apple API, local requires APP_STORE_REPORT_LOCAL_DIR",
    ] = "auto",
) -> str:
    """Get daily install statistics. Differentiates new downloads, updates, and re-downloads."""
    try:
        result = await get_install_stats(_get_client(require_auth=source != "local"), date, group_by, source)
        return _result(result)
    except ApiError as e:
        return e.to_user_message()
    except ReportSourceError as e:
        return str(e)


@mcp.tool(name="get_sales_report")
async def get_sales_report_tool(
    report_date: Annotated[str, "Report date (YYYY-MM-DD for daily, YYYY-MM for monthly)"],
    report_sub_type: Annotated[
        Literal["SUMMARY", "SUBSCRIPTION", "SUBSCRIPTION_EVENT", "SUBSCRIBER"],
        "Report sub-type",
    ] = "SUMMARY",
    date_type: Annotated[
        Literal["DAILY", "WEEKLY", "MONTHLY", "YEARLY"],
        "Report frequency",
    ] = "DAILY",
    source: Annotated[
        Literal["auto", "api", "local"],
        "Data source: auto prefers local archive, api forces Apple API, local requires APP_STORE_REPORT_LOCAL_DIR",
    ] = "auto",
) -> str:
    """Get raw sales report data parsed as structured JSON with transformed/local-style headers."""
    try:
        result = await get_sales_report(
            _get_client(require_auth=source != "local"),
            report_date,
            report_sub_type,
            date_type,
            source,
        )
        return _result(result)
    except ApiError as e:
        return e.to_user_message()
    except ReportSourceError as e:
        return str(e)


@mcp.tool(name="get_subscription_report")
async def get_subscription_report_tool(
    report_date: Annotated[str, "Report date in YYYY-MM-DD format"],
    report_type: Annotated[
        Literal["SUBSCRIPTION", "SUBSCRIPTION_EVENT", "SUBSCRIBER", "SUBSCRIPTION_OFFER_REDEMPTION"],
        "Subscription report type",
    ] = "SUBSCRIPTION",
    report_sub_type: Annotated[
        Literal["SUMMARY", "DETAILED", "SUMMARY_INSTALL_TYPE", "SUMMARY_TERRITORY", "SUMMARY_CHANNEL"],
        "Report sub-type",
    ] = "SUMMARY",
    date_type: Annotated[
        Literal["DAILY", "WEEKLY", "MONTHLY", "YEARLY"],
        "Report frequency",
    ] = "DAILY",
    source: Annotated[
        Literal["auto", "api", "local"],
        "Data source: auto prefers local archive, api forces Apple API, local requires APP_STORE_REPORT_LOCAL_DIR",
    ] = "auto",
) -> str:
    """Get subscription report data (active subscribers, trials, events) with transformed/local-style headers."""
    try:
        result = await get_subscription_report(
            _get_client(require_auth=source != "local"),
            report_date,
            report_type,
            report_sub_type,
            date_type,
            source,
        )
        return _result(result)
    except ApiError as e:
        return e.to_user_message()
    except ReportSourceError as e:
        return str(e)


@mcp.tool(name="get_finance_report")
async def get_finance_report_tool(
    report_date: Annotated[str, "Report date in YYYY-MM format (e.g. 2026-03)"],
    region_code: Annotated[str, "Region code (ZZ for all regions, US, EU, JP, etc.)"] = "ZZ",
    source: Annotated[
        Literal["auto", "api", "local"],
        "Data source: auto prefers local archive, api forces Apple API, local requires APP_STORE_REPORT_LOCAL_DIR",
    ] = "auto",
) -> str:
    """Get financial/settlement report by region. Returns earnings, payments, and transaction details."""
    try:
        result = await get_finance_report(
            _get_client(require_auth=source != "local"),
            report_date,
            region_code,
            source,
        )
        return _result(result)
    except ApiError as e:
        return e.to_user_message()
    except ReportSourceError as e:
        return str(e)


@mcp.tool(name="list_local_reports")
def list_local_reports_tool(
    report_type: Annotated[
        Literal["SALES", "SUBSCRIPTION", "SUBSCRIPTION_EVENT", "SUBSCRIBER", "SUBSCRIPTION_OFFER_REDEMPTION", "FINANCIAL"] | None,
        "Optional report type filter for local archive discovery",
    ] = None,
    report_sub_type: Annotated[str | None, "Optional report sub-type filter such as SUMMARY or DETAILED"] = None,
    date_type: Annotated[
        Literal["DAILY", "WEEKLY", "MONTHLY", "YEARLY"] | None,
        "Optional report frequency filter",
    ] = None,
    report_date_prefix: Annotated[str, "Optional date prefix such as 2024-03 or 2024-04-08"] = "",
    region_code: Annotated[str | None, "Optional finance region filter such as ZZ or US"] = None,
    vendor_number: Annotated[str | None, "Optional vendor number filter if embedded in file names"] = None,
    path_prefix: Annotated[str, "Optional relative path prefix under APP_STORE_REPORT_LOCAL_DIR"] = "",
    max_results: Annotated[int, "Maximum number of files to return (1-500)"] = 50,
) -> str:
    """List locally archived report files under APP_STORE_REPORT_LOCAL_DIR."""
    try:
        result = list_local_reports_from_archive(
            report_type=report_type,
            report_sub_type=report_sub_type,
            date_type=date_type,
            report_date_prefix=report_date_prefix,
            region_code=region_code,
            vendor_number=vendor_number,
            path_prefix=path_prefix,
            max_results=max_results,
        )
        return _result(result)
    except ReportSourceError as e:
        return str(e)


@mcp.tool(name="get_app_downloads_report")
async def get_app_downloads_report_tool(
    app_id: Annotated[str, "Apple app ID (numeric identifier)"],
    report_date: Annotated[str, "Report date in YYYY-MM-DD format (e.g. 2026-04-08)"],
    group_by: Annotated[
        Literal["app", "territory", "download_type", "source_type"],
        "Dimension to group downloads by",
    ] = "download_type",
    granularity: Annotated[
        Literal["DAILY", "WEEKLY", "MONTHLY"],
        "Report instance granularity (WEEKLY/MONTHLY only supported for the Detailed report)",
    ] = "DAILY",
    detailed: Annotated[
        bool,
        "Use the 'App Downloads Detailed' report instead of the Standard one",
    ] = True,
    access_type: Annotated[
        Literal["ONGOING", "ONE_TIME_SNAPSHOT"],
        "ONGOING covers data from ~24-48h after the report request was first created, onward. "
        "Use ONE_TIME_SNAPSHOT for historical dates before that (Apple generally retains data "
        "back to 2024-01-01) - it creates a one-off backfill request, no new data after that.",
    ] = "ONGOING",
) -> str:
    """Get App Store Downloads counts via the Analytics Reports API, with aggregation by app, territory, download type, or source type."""
    try:
        result = await get_app_downloads_report(
            _get_client(),
            app_id,
            report_date,
            group_by,
            granularity,
            detailed,
            access_type,
        )
        return _result(result)
    except AnalyticsReportNotReadyError as e:
        return str(e)
    except ApiError as e:
        if e.status_code == 403:
            return (
                "Creating or accessing this Analytics Report Request requires the Admin role "
                "on this App Store Connect API key. Ask an Admin to grant access, or use a key "
                "with Admin permissions."
            )
        return e.to_user_message()


@mcp.tool(name="debug_list_app_downloads_instances")
async def debug_list_app_downloads_instances_tool(
    app_id: Annotated[str, "Apple app ID (numeric identifier)"],
    detailed: Annotated[bool, "Look up the Detailed report instead of the Standard one"] = True,
    granularity: Annotated[
        Literal["DAILY", "WEEKLY", "MONTHLY"], "Report instance granularity"
    ] = "DAILY",
    access_type: Annotated[
        Literal["ONGOING", "ONE_TIME_SNAPSHOT"],
        "Which analyticsReportRequest to inspect",
    ] = "ONGOING",
) -> str:
    """TEMPORARY diagnostic tool: finds the App Downloads report id for an app under the given
    access_type's report request, then dumps the raw, unfiltered analyticsReportInstances list
    (no processingDate filter) so we can see which dates actually have generated instances, and
    whether the report itself has appeared yet. Remove once ONE_TIME_SNAPSHOT backfill timing is
    understood."""
    try:
        client = _get_client()
        request_id = await ensure_report_request(client, app_id, access_type=access_type)
        reports = await client.list_analytics_reports(request_id)
        report_id = None
        for item in reports.get("data", []):
            name = (item.get("attributes", {}).get("name") or "").strip().lower()
            if "app downloads" not in name:
                continue
            if ("detailed" in name) == detailed:
                report_id = item.get("id")
                break
        if report_id is None:
            return _result({"report_request_id": request_id, "error": "report not found", "reports": reports})
        instances = await client.list_report_instances(report_id, granularity=granularity)
        return _result({"report_request_id": request_id, "report_id": report_id, "instances": instances})
    except AnalyticsReportNotReadyError as e:
        return str(e)
    except ApiError as e:
        if e.status_code == 403:
            return (
                "Creating or accessing this Analytics Report Request requires the Admin role "
                "on this App Store Connect API key. Ask an Admin to grant access, or use a key "
                "with Admin permissions."
            )
        return e.to_user_message()


@mcp.tool(name="debug_dump_app_downloads_segment")
async def debug_dump_app_downloads_segment_tool(
    app_id: Annotated[str, "Apple app ID (numeric identifier)"],
    report_date: Annotated[str, "Report date in YYYY-MM-DD format (e.g. 2026-08-07)"],
    detailed: Annotated[bool, "Use the 'App Downloads Detailed' report instead of the Standard one"] = True,
    granularity: Annotated[
        Literal["DAILY", "WEEKLY", "MONTHLY"], "Report instance granularity"
    ] = "DAILY",
    access_type: Annotated[
        Literal["ONGOING", "ONE_TIME_SNAPSHOT"],
        "Which analyticsReportRequest to inspect",
    ] = "ONGOING",
    sample_size: Annotated[int, "Number of raw sample rows to include (1-20)"] = 5,
) -> str:
    """TEMPORARY diagnostic tool: proves whether a given app_id's App Downloads segment for a
    specific date actually carries per-Territory data that sums to the app's worldwide total.
    Returns: the analyticsReportRequest's bound app_id, the matched report name, the raw file
    header, a few raw sample rows, whether Territory/App Name/App Apple Identifier/SKU-like
    columns are present, a Territory-level counts breakdown with its sum, and the overall
    (worldwide) counts sum for the same rows - so the two sums can be compared directly."""
    try:
        client = _get_client()
        segment_urls = await resolve_app_downloads_segment_urls(
            client,
            app_id,
            report_date,
            granularity=granularity,
            detailed=detailed,
            access_type=access_type,
        )

        header: list[str] = []
        raw_sample_rows: list[dict[str, str]] = []
        all_rows: list[dict] = []
        for url in segment_urls:
            raw = await client.fetch_analytics_segment(url)
            lines = [line for line in raw.splitlines() if line.strip()]
            if lines and not header:
                header = lines[0].split("\t") if "\t" in lines[0] else lines[0].split(",")
            raw_rows = parse_tsv(raw)
            if not raw_sample_rows:
                raw_sample_rows = raw_rows[:sample_size]
            all_rows.extend(parse_app_downloads_report(raw))

        territory_breakdown: dict[str, int] = {}
        ww_total = 0
        app_ids_seen: set[str] = set()
        app_names_seen: set[str] = set()
        for row in all_rows:
            counts = int(row.get("counts") or 0)
            ww_total += counts
            territory = row.get("territory") or "Unknown"
            territory_breakdown[territory] = territory_breakdown.get(territory, 0) + counts
            if row.get("app_apple_identifier"):
                app_ids_seen.add(str(row.get("app_apple_identifier")))
            if row.get("app_name"):
                app_names_seen.add(str(row.get("app_name")))

        territory_sum = sum(territory_breakdown.values())

        return _result(
            {
                "requested_app_id": app_id,
                "app_apple_identifiers_in_rows": sorted(app_ids_seen),
                "app_names_in_rows": sorted(app_names_seen),
                "report_date": report_date,
                "access_type": access_type,
                "header": header,
                "sample_rows": raw_sample_rows,
                "territory_field_present": "territory" in header
                or any("territory" in h.lower() for h in header),
                "territory_breakdown": dict(
                    sorted(territory_breakdown.items(), key=lambda kv: kv[1], reverse=True)
                ),
                "territory_sum": territory_sum,
                "ww_total": ww_total,
                "territory_sum_matches_ww_total": territory_sum == ww_total,
            }
        )
    except AnalyticsReportNotReadyError as e:
        return str(e)
    except ApiError as e:
        if e.status_code == 403:
            return (
                "Creating or accessing this Analytics Report Request requires the Admin role "
                "on this App Store Connect API key. Ask an Admin to grant access, or use a key "
                "with Admin permissions."
            )
        return e.to_user_message()


@mcp.tool(name="get_customer_reviews")
async def get_customer_reviews_tool(
    app_id: Annotated[str, "Apple app ID (numeric identifier)"],
    limit: Annotated[int, "Number of reviews to return (max 200)"] = 20,
    sort: Annotated[
        Literal["createdDate", "-createdDate", "rating", "-rating"],
        "Sort order (prefix with - for descending)",
    ] = "-createdDate",
    rating: Annotated[int | None, "Filter by specific star rating (1-5)"] = None,
) -> str:
    """Get customer reviews for an app. Supports filtering by rating and sorting."""
    try:
        result = await get_customer_reviews(_get_client(), app_id, limit, sort, rating)
        return _result(result)
    except ApiError as e:
        return e.to_user_message()
