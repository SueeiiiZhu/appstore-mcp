"""Exchange rate lookup tool: realtime (today) and historical rates to USD."""

import datetime
from typing import Any

from ..exchange import fetch_historical_rates_to_usd, get_rates_to_usd


def _today_utc() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


async def get_exchange_rates(date: str, currency: str | None = None) -> dict[str, Any]:
    """Get exchange-to-USD rates for a given date.

    If `date` equals today's date (UTC), returns realtime rates (open.er-api.com).
    Otherwise, returns historical ECB reference rates (frankfurter.app) for that date.
    If `currency` is provided, filters the response to that currency's rate only
    (plus USD=1.0 for context).
    """
    requested_date = date
    today = _today_utc()

    result: dict[str, Any] = {"requested_date": requested_date}

    if requested_date == today.isoformat():
        rates = await get_rates_to_usd(requested_date)
        result["fx_source"] = "open.er-api.com (realtime)"
        result["fx_fetched_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        result["disclaimer"] = (
            "These are CURRENT/realtime exchange rates, not rates as-of the requested date. "
            "NOT Apple's official exchange rate. Actual payment amounts may differ."
        )
    else:
        rates, actual_date = await fetch_historical_rates_to_usd(requested_date)
        result["fx_source"] = "frankfurter.app (ECB historical reference rates)"
        result["fx_as_of"] = actual_date
        result["disclaimer"] = (
            "ECB reference rates are a reference/approximation, NOT Apple's actual "
            "settlement/official exchange rate. If the requested date wasn't an ECB "
            "business day, fx_as_of reflects the most recent prior business day used."
        )

    if currency is not None:
        currency_code = currency.upper()
        if currency_code not in rates:
            raise ValueError(
                f"Currency code '{currency}' not found in exchange rates. "
                f"Available codes: {', '.join(sorted(rates.keys()))}"
            )
        result["currency"] = currency_code
        result["rate"] = rates[currency_code]
        result["usd"] = 1.0
    else:
        result["rates"] = rates

    return result
