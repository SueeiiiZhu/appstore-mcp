"""Subscription report tool."""

from typing import Any, Callable

from ..cache import ReportCache
from ..client import ApiClient
from ..parsers import (
    format_sales_report_rows,
    format_subscription_event_report_rows,
    format_subscription_report_rows,
    parse_sales_report,
    parse_subscription_event_report,
    parse_subscription_report,
)
from ..report_source import ReportSource, load_report_text, resolve_sales_report_source

_cache = ReportCache()

# Latest known report versions per type
_VERSIONS = {
    "SUBSCRIPTION": "1_4",
    "SUBSCRIPTION_EVENT": "1_3",
    "SUBSCRIBER": "1_4",
    "SUBSCRIPTION_OFFER_REDEMPTION": "1_1",
}


ParserFn = Callable[[str], list[dict[str, Any]]]
FormatterFn = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


def _subscription_report_handlers(report_type: str) -> tuple[ParserFn, FormatterFn]:
    if report_type == "SUBSCRIPTION":
        return parse_subscription_report, format_subscription_report_rows
    if report_type == "SUBSCRIPTION_EVENT":
        return parse_subscription_event_report, format_subscription_event_report_rows
    return parse_sales_report, format_sales_report_rows


async def _get_subscription_rows_internal(
    client: ApiClient,
    report_date: str,
    report_type: str = "SUBSCRIPTION",
    report_sub_type: str = "SUMMARY",
    date_type: str = "DAILY",
    source: ReportSource = "auto",
) -> list[dict[str, Any]]:
    version = _VERSIONS.get(report_type, "1_0")
    location = resolve_sales_report_source(
        client,
        report_date,
        report_type=report_type,
        report_sub_type=report_sub_type,
        date_type=date_type,
        source=source,
        version=version,
    )
    cache_key = (
        f"sub:{report_type}:{report_sub_type}:{date_type}:{report_date}:{client.vendor_number}:"
        f"{location.cache_fragment}"
    )
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    raw = await load_report_text(client, location)
    parser, _ = _subscription_report_handlers(report_type)
    rows = parser(raw)

    _cache.set(cache_key, rows)
    return rows


async def get_subscription_report(
    client: ApiClient,
    report_date: str,
    report_type: str = "SUBSCRIPTION",
    report_sub_type: str = "SUMMARY",
    date_type: str = "DAILY",
    source: ReportSource = "auto",
) -> list[dict[str, Any]]:
    rows = await _get_subscription_rows_internal(
        client,
        report_date,
        report_type,
        report_sub_type,
        date_type,
        source,
    )
    _, formatter = _subscription_report_handlers(report_type)
    return formatter(rows)
