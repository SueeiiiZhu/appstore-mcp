"""Revenue summary tool."""

import logging
from typing import Any

from ..client import ApiClient
from ..exchange import convert_to_usd, get_rates_to_usd
from ..report_source import ReportSource
from .sales import get_sales_report

logger = logging.getLogger(__name__)


def _group_key_fn(group_by: str):
    match group_by:
        case "country":
            return lambda row: row["country_code"]
        case "device":
            return lambda row: row.get("device") or "Unknown"
        case _:
            return lambda row: row.get("title") or row.get("sku", "Unknown")


async def get_revenue_summary(
    client: ApiClient,
    date: str,
    group_by: str = "app",
    source: ReportSource = "auto",
) -> dict[str, Any]:
    rows = await get_sales_report(client, date, "SUMMARY", "DAILY", source)
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
