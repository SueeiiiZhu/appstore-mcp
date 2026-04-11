"""Currency exchange rates with caching."""

import time

import httpx

# Cache: {date_str: {currency: rate_to_usd}}
_rate_cache: dict[str, dict[str, float]] = {}
_CACHE_TTL = 3600  # 1 hour
_cache_timestamps: dict[str, float] = {}

_API_URL = "https://open.er-api.com/v6/latest/USD"


async def get_rates_to_usd(date: str | None = None) -> dict[str, float]:
    """Fetch exchange rates to USD.

    Note: open.er-api.com only provides latest rates (no historical).
    The date parameter is used as cache key only.

    Returns a dict mapping currency code → amount in USD.
    e.g. {"EUR": 1.08, "INR": 0.012, "USD": 1.0}
    """
    cache_key = date or "latest"

    if cache_key in _rate_cache:
        if time.monotonic() - _cache_timestamps[cache_key] < _CACHE_TTL:
            return _rate_cache[cache_key]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_API_URL)
        resp.raise_for_status()
        data = resp.json()

    # data["rates"] = {"EUR": 0.92, "INR": 83.5, ...} (how much 1 USD buys)
    # We want the inverse: how much USD per 1 unit of currency
    rates_to_usd: dict[str, float] = {"USD": 1.0}
    for currency, rate in data["rates"].items():
        if rate > 0:
            rates_to_usd[currency] = 1.0 / rate

    _rate_cache[cache_key] = rates_to_usd
    _cache_timestamps[cache_key] = time.monotonic()
    return rates_to_usd


def convert_to_usd(amount: float, currency: str, rates: dict[str, float]) -> float:
    """Convert an amount to USD using pre-fetched rates."""
    if currency == "USD":
        return amount
    rate = rates.get(currency)
    if rate is None:
        return amount  # fallback: return as-is if unknown currency
    return amount * rate
