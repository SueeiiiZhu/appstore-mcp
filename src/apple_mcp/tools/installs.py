"""Install statistics tool."""

from typing import Any

from ..client import ApiClient
from ..parsers import INSTALL_PRODUCT_TYPES, REDOWNLOAD_PRODUCT_TYPES, UPDATE_PRODUCT_TYPES
from ..report_source import ReportSource
from .sales import _get_sales_rows_internal


def _group_key_fn(group_by: str):
    match group_by:
        case "country":
            return lambda row: row["country_code"]
        case "device":
            return lambda row: row.get("device") or "Unknown"
        case _:
            return lambda row: row.get("title") or row.get("sku", "Unknown")


async def get_install_stats(
    client: ApiClient,
    date: str,
    group_by: str = "app",
    source: ReportSource = "auto",
) -> dict[str, Any]:
    rows = await _get_sales_rows_internal(client, date, "SUMMARY", "DAILY", source)
    key_fn = _group_key_fn(group_by)

    groups: dict[str, dict[str, int]] = {}
    total_units = 0

    for row in rows:
        ptype = row["product_type_identifier"]
        key = key_fn(row)
        g = groups.setdefault(key, {"new_downloads": 0, "updates": 0, "redownloads": 0})
        units = int(row["units"])

        if ptype in INSTALL_PRODUCT_TYPES:
            g["new_downloads"] += units
            total_units += units
        elif ptype in UPDATE_PRODUCT_TYPES:
            g["updates"] += units
            total_units += units
        elif ptype in REDOWNLOAD_PRODUCT_TYPES:
            g["redownloads"] += units
            total_units += units

    breakdown = [
        {"key": k, **v}
        for k, v in groups.items()
        if v["new_downloads"] + v["updates"] + v["redownloads"] > 0
    ]
    breakdown.sort(key=lambda x: x["new_downloads"], reverse=True)

    return {"total_units": total_units, "breakdown": breakdown}
