"""Revenue summary tool."""

from typing import Any

from ..cache import ReportCache
from ..client import ApiClient
from ..parsers import parse_sales_report

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

    groups: dict[str, dict[str, float]] = {}
    total_proceeds = 0.0
    total_units = 0
    currency = "USD"

    for row in rows:
        proceeds = row["developer_proceeds"] * row["units"]
        total_proceeds += proceeds
        total_units += int(row["units"])
        currency = row.get("currency_of_proceeds") or currency

        key = key_fn(row)
        g = groups.setdefault(key, {"proceeds": 0.0, "units": 0})
        g["proceeds"] += proceeds
        g["units"] += int(row["units"])

    breakdown = sorted(
        [{"key": k, "proceeds": round(v["proceeds"], 2), "units": int(v["units"])} for k, v in groups.items()],
        key=lambda x: x["proceeds"],
        reverse=True,
    )

    return {
        "total_proceeds": round(total_proceeds, 2),
        "currency": currency,
        "total_units": total_units,
        "breakdown": breakdown,
    }
