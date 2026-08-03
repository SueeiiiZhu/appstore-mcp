"""App Store Downloads (Analytics Reports) tool."""

from typing import Any

from ..analytics_report_source import resolve_app_downloads_segment_urls
from ..cache import ReportCache
from ..client import ApiClient
from ..parsers import parse_app_downloads_report

_cache = ReportCache()


def _group_key_fn(group_by: str):
    match group_by:
        case "app":
            return lambda row: row.get("app_name") or "Unknown"
        case "territory":
            return lambda row: row.get("territory") or "Unknown"
        case "source_type":
            return lambda row: row.get("source_type") or "Unknown"
        case _:
            return lambda row: row.get("download_type") or "Unknown"


async def _get_app_downloads_rows_internal(
    client: ApiClient,
    app_id: str,
    report_date: str,
    granularity: str = "DAILY",
    detailed: bool = True,
) -> list[dict[str, Any]]:
    cache_key = f"app_downloads:{app_id}:{report_date}:{granularity}:{detailed}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # Segment URLs are pre-signed and expire - never cache them, only the parsed rows below.
    segment_urls = await resolve_app_downloads_segment_urls(
        client,
        app_id,
        report_date,
        granularity=granularity,
        detailed=detailed,
    )

    rows: list[dict[str, Any]] = []
    for url in segment_urls:
        raw = await client.fetch_analytics_segment(url)
        rows.extend(parse_app_downloads_report(raw))

    _cache.set(cache_key, rows)
    return rows


async def get_app_downloads_report(
    client: ApiClient,
    app_id: str,
    report_date: str,
    group_by: str = "download_type",
    granularity: str = "DAILY",
    detailed: bool = True,
) -> dict[str, Any]:
    rows = await _get_app_downloads_rows_internal(
        client, app_id, report_date, granularity, detailed
    )
    key_fn = _group_key_fn(group_by)

    groups: dict[str, int] = {}
    total_downloads = 0

    for row in rows:
        counts = int(row.get("counts") or 0)
        total_downloads += counts
        key = key_fn(row)
        groups[key] = groups.get(key, 0) + counts

    breakdown = sorted(
        [{"key": k, "counts": v} for k, v in groups.items()],
        key=lambda x: x["counts"],
        reverse=True,
    )

    return {"total_downloads": total_downloads, "breakdown": breakdown}
