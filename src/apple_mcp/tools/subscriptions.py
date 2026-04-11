"""Subscription report tool."""

from typing import Any

from ..cache import ReportCache
from ..client import ApiClient
from ..parsers import parse_sales_report, parse_subscription_event_report, parse_subscription_report

_cache = ReportCache()


async def get_subscription_report(
    client: ApiClient,
    report_date: str,
    report_type: str = "SUBSCRIPTION",
    report_sub_type: str = "SUMMARY",
    date_type: str = "DAILY",
) -> list[dict[str, Any]]:
    cache_key = f"sub:{report_type}:{report_sub_type}:{date_type}:{report_date}:{client.vendor_number}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # Latest known report versions per type
    _VERSIONS = {
        "SUBSCRIPTION": "1_4",
        "SUBSCRIPTION_EVENT": "1_3",
        "SUBSCRIBER": "1_4",
        "SUBSCRIPTION_OFFER_REDEMPTION": "1_1",
    }
    version = _VERSIONS.get(report_type, "1_0")

    raw = await client.fetch_gzipped_report(
        "/v1/salesReports",
        {
            "filter[vendorNumber]": client.vendor_number,
            "filter[reportType]": report_type,
            "filter[reportSubType]": report_sub_type,
            "filter[reportDate]": report_date,
            "filter[frequency]": date_type,
            "filter[version]": version,
        },
    )
    # Use the appropriate parser based on report type
    if report_type == "SUBSCRIPTION":
        rows = parse_subscription_report(raw)
    elif report_type == "SUBSCRIPTION_EVENT":
        rows = parse_subscription_event_report(raw)
    else:
        # SUBSCRIBER and SUBSCRIPTION_OFFER_REDEMPTION: use generic TSV parser
        rows = parse_sales_report(raw)

    _cache.set(cache_key, rows)
    return rows
