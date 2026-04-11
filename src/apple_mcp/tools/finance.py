"""Finance report tool."""

from typing import Any

from ..cache import ReportCache
from ..client import ApiClient
from ..parsers import parse_finance_report

_cache = ReportCache()


async def get_finance_report(
    client: ApiClient,
    report_date: str,
    region_code: str = "ZZ",
) -> list[dict[str, Any]]:
    cache_key = f"finance:{report_date}:{region_code}:{client.vendor_number}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    raw = await client.fetch_gzipped_report(
        "/v1/financeReports",
        {
            "filter[vendorNumber]": client.vendor_number,
            "filter[reportType]": "FINANCIAL",
            "filter[reportDate]": report_date,
            "filter[regionCode]": region_code,
        },
    )
    rows = parse_finance_report(raw)
    _cache.set(cache_key, rows)
    return rows
