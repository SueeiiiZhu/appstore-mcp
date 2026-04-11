"""Revenue summary tool."""

import logging
from typing import Any

from ..cache import ReportCache
from ..client import ApiClient
from ..exchange import convert_to_usd, get_rates_to_usd
from ..parsers import parse_sales_report

logger = logging.getLogger(__name__)

_cache = ReportCache()


async def _fetch_sales_rows(client: ApiClient, date: str) -> list[dict[str, Any]]:
    cache_key = f"sales:SUMMARY:DAILY:{date}:{client.vendor_number}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    raw = await client.fetch_gzipped_report(
        "/v1/salesReports",
        {
            "filter[vendorNumber]": client.vendor_number,
            "filter[reportType]": "SALES",
            "filter[reportSubType]": "SUMMARY",
            "filter[reportDate]": date,
            "filter[frequency]": "DAILY",
        },
    )
    rows = parse_sales_report(raw)
    _cache.set(cache_key, rows)
    return rows


def _group_key_fn(group_by: str):
    match group_by:
        case "country":
            return lambda row: row["country_code"]
        case "device":
            return lambda row: row.get("device") or "Unknown"
        case _:
            return lambda row: row.get("title") or row.get("sku", "Unknown")


async def get_revenue_summary(
    client: ApiClient, date: str, group_by: str = "app"
) -> dict[str, Any]:
    rows = await _fetch_sales_rows(client, date)
    key_fn = _group_key_fn(group_by)

    # Fetch exchange rates for the report date to normalize to USD
    try:
        rates = await get_rates_to_usd(date)
    except Exception:
        logger.warning("Failed to fetch exchange rates, falling back to raw amounts")
        rates = {}

    groups: dict[str, dict[str, float]] = {}
    total_proceeds_usd = 0.0
    total_units = 0

    for row in rows:
        currency = row.get("currency_of_proceeds") or "USD"
        proceeds_local = row["developer_proceeds"] * row["units"]
        proceeds_usd = convert_to_usd(proceeds_local, currency, rates)

        total_proceeds_usd += proceeds_usd
        total_units += int(row["units"])

        key = key_fn(row)
        g = groups.setdefault(key, {"proceeds_usd": 0.0, "units": 0})
        g["proceeds_usd"] += proceeds_usd
        g["units"] += int(row["units"])

    breakdown = sorted(
        [{"key": k, "proceeds_usd": round(v["proceeds_usd"], 2), "units": int(v["units"])} for k, v in groups.items()],
        key=lambda x: x["proceeds_usd"],
        reverse=True,
    )

    result: dict[str, Any] = {
        "total_proceeds_usd": round(total_proceeds_usd, 2),
        "currency": "USD",
        "total_units": total_units,
        "breakdown": breakdown,
    }

    if rates:
        result["disclaimer"] = (
            "USD amounts use third-party exchange rates (open.er-api.com), "
            "NOT Apple's official exchange rate. Actual payment amounts may differ. "
            "Please refer to Apple's official payment details for accurate figures."
        )

    return result
