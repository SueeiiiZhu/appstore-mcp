"""MCP server definition with tool registration."""

import json
import os
import sys
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP

from .client import ApiClient, ApiError
from .tools.finance import get_finance_report
from .tools.installs import get_install_stats
from .tools.revenue import get_revenue_summary
from .tools.reviews import get_customer_reviews
from .tools.sales import get_sales_report
from .tools.subscriptions import get_subscription_report

mcp = FastMCP("apple-appstore-reports")

_client: ApiClient | None = None


def _get_client() -> ApiClient:
    global _client
    if _client is None:
        _client = ApiClient(
            issuer_id=_require_env("APP_STORE_CONNECT_ISSUER_ID"),
            key_id=_require_env("APP_STORE_CONNECT_KEY_ID"),
            private_key_path=_require_env("APP_STORE_CONNECT_PRIVATE_KEY_PATH"),
            vendor_number=_require_env("APP_STORE_CONNECT_VENDOR_NUMBER"),
        )
    return _client


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
) -> str:
    """Get daily revenue summary with aggregation. Returns total proceeds and breakdown by app, country, or device."""
    try:
        result = await get_revenue_summary(_get_client(), date, group_by)
        return _result(result)
    except ApiError as e:
        return e.to_user_message()


@mcp.tool(name="get_install_stats")
async def get_install_stats_tool(
    date: Annotated[str, "Report date in YYYY-MM-DD format (e.g. 2026-04-08)"],
    group_by: Annotated[
        Literal["app", "country", "device"],
        "Dimension to group installs by",
    ] = "app",
) -> str:
    """Get daily install statistics. Differentiates new downloads, updates, and re-downloads."""
    try:
        result = await get_install_stats(_get_client(), date, group_by)
        return _result(result)
    except ApiError as e:
        return e.to_user_message()


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
) -> str:
    """Get raw sales report data parsed as structured JSON."""
    try:
        result = await get_sales_report(_get_client(), report_date, report_sub_type, date_type)
        return _result(result)
    except ApiError as e:
        return e.to_user_message()


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
) -> str:
    """Get subscription report data (active subscribers, trials, events)."""
    try:
        result = await get_subscription_report(_get_client(), report_date, report_type, report_sub_type, date_type)
        return _result(result)
    except ApiError as e:
        return e.to_user_message()


@mcp.tool(name="get_finance_report")
async def get_finance_report_tool(
    report_date: Annotated[str, "Report date in YYYY-MM format (e.g. 2026-03)"],
    region_code: Annotated[str, "Region code (ZZ for all regions, US, EU, JP, etc.)"] = "ZZ",
) -> str:
    """Get financial/settlement report by region. Returns earnings, payments, and transaction details."""
    try:
        result = await get_finance_report(_get_client(), report_date, region_code)
        return _result(result)
    except ApiError as e:
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
