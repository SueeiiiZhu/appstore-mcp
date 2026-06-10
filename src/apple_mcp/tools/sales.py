"""Raw sales report tool."""

from typing import Any

from ..cache import ReportCache
from ..client import ApiClient
from ..parsers import format_sales_report_rows, parse_sales_report
from ..report_source import ReportSource, load_report_text, resolve_sales_report_source

_cache = ReportCache()


async def _get_sales_rows_internal(
    client: ApiClient,
    report_date: str,
    report_sub_type: str = "SUMMARY",
    date_type: str = "DAILY",
    source: ReportSource = "auto",
) -> list[dict[str, Any]]:
    location = resolve_sales_report_source(
        client,
        report_date,
        report_type="SALES",
        report_sub_type=report_sub_type,
        date_type=date_type,
        source=source,
    )
    cache_key = (
        f"sales:{report_sub_type}:{date_type}:{report_date}:{client.vendor_number}:"
        f"{location.cache_fragment}"
    )
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    raw = await load_report_text(client, location)
    rows = parse_sales_report(raw)
    _cache.set(cache_key, rows)
    return rows


async def get_sales_report(
    client: ApiClient,
    report_date: str,
    report_sub_type: str = "SUMMARY",
    date_type: str = "DAILY",
    source: ReportSource = "auto",
) -> list[dict[str, Any]]:
    rows = await _get_sales_rows_internal(
        client,
        report_date,
        report_sub_type,
        date_type,
        source,
    )
    return format_sales_report_rows(rows)
