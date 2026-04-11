"""Raw sales report tool."""

from typing import Any

from ..cache import ReportCache
from ..client import ApiClient
from ..parsers import parse_sales_report

_cache = ReportCache()


async def get_sales_report(
    client: ApiClient,
    report_date: str,
    report_sub_type: str = "SUMMARY",
    date_type: str = "DAILY",
) -> list[dict[str, Any]]:
    cache_key = f"sales:{report_sub_type}:{date_type}:{report_date}:{client.vendor_number}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    raw = await client.fetch_gzipped_report(
        "/v1/salesReports",
        {
            "filter[vendorNumber]": client.vendor_number,
            "filter[reportType]": "SALES",
            "filter[reportSubType]": report_sub_type,
            "filter[reportDate]": report_date,
            "filter[frequency]": date_type,
        },
    )
    rows = parse_sales_report(raw)
    _cache.set(cache_key, rows)
    return rows
