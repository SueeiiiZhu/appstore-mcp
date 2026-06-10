"""Finance report tool."""

import logging
from typing import Any

from ..cache import ReportCache
from ..client import ApiClient
from ..exchange import convert_to_usd, get_rates_to_usd
from ..parsers import parse_finance_report
from ..report_source import ReportSource, load_report_text, resolve_finance_report_source

logger = logging.getLogger(__name__)

_cache = ReportCache()


async def get_finance_report(
    client: ApiClient,
    report_date: str,
    region_code: str = "ZZ",
    source: ReportSource = "auto",
) -> dict[str, Any]:
    location = resolve_finance_report_source(client, report_date, region_code, source)
    cache_key = f"finance:{report_date}:{region_code}:{client.vendor_number}:{location.cache_fragment}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    raw = await load_report_text(client, location)
    rows = parse_finance_report(raw)

    # Separate summary rows (Total_Rows, Total_Amount, Total_Units) from data rows
    data_rows = []
    for row in rows:
        if row.get("start_date", "").startswith("Total_"):
            continue
        data_rows.append(row)

    # Aggregate by currency
    by_currency: dict[str, float] = {}
    for row in data_rows:
        currency = row.get("partner_share_currency") or "Unknown"
        amount = row.get("extended_partner_share", 0.0)
        by_currency[currency] = by_currency.get(currency, 0.0) + amount

    by_currency = {k: round(v, 2) for k, v in by_currency.items() if k}

    # Estimate USD total using third-party exchange rates
    try:
        rates = await get_rates_to_usd(report_date)
    except Exception:
        logger.warning("Failed to fetch exchange rates, skipping USD estimation")
        rates = {}

    estimated_total_usd = 0.0
    currency_details = []
    has_rates = bool(rates)

    for currency, amount in sorted(by_currency.items(), key=lambda x: abs(x[1]), reverse=True):
        detail: dict[str, Any] = {"currency": currency, "amount": round(amount, 2)}
        if has_rates:
            usd = convert_to_usd(amount, currency, rates)
            detail["estimated_usd"] = round(usd, 2)
            estimated_total_usd += usd
        currency_details.append(detail)

    result: dict[str, Any] = {
        "report_date": report_date,
        "region_code": region_code,
        "by_currency": currency_details,
        "total_rows": len(data_rows),
    }

    if has_rates:
        result["estimated_total_usd"] = round(estimated_total_usd, 2)
        result["disclaimer"] = (
            "USD estimates use third-party exchange rates (open.er-api.com), "
            "NOT Apple's official exchange rate. Actual payment amounts may differ. "
            "Please refer to Apple's official payment details for accurate figures."
        )

    _cache.set(cache_key, result)
    return result
