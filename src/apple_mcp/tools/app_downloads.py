"""App Store Downloads (Analytics Reports) tool."""

from typing import Any

from ..analytics_report_source import ResolvedSegments, resolve_app_downloads_segments
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
    access_type: str = "ONGOING",
) -> tuple[list[dict[str, Any]], ResolvedSegments]:
    cache_key = f"app_downloads:{app_id}:{report_date}:{granularity}:{detailed}:{access_type}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # Segment URLs are pre-signed and expire - never cache them, only the parsed rows below.
    resolved = await resolve_app_downloads_segments(
        client,
        app_id,
        report_date,
        granularity=granularity,
        detailed=detailed,
        access_type=access_type,
    )

    rows: list[dict[str, Any]] = []
    for url in resolved.urls:
        raw = await client.fetch_analytics_segment(url)
        rows.extend(parse_app_downloads_report(raw))

    result = (rows, resolved)
    _cache.set(cache_key, result)
    return result


async def get_app_downloads_report(
    client: ApiClient,
    app_id: str,
    report_date: str,
    group_by: str = "download_type",
    granularity: str = "DAILY",
    detailed: bool = True,
    access_type: str = "ONGOING",
    business_date: str | None = None,
) -> dict[str, Any]:
    """Get App Store Downloads, optionally filtered to a single raw business_date.

    report_date selects the Apple analyticsReportInstance (by processingDate);
    an instance can still contain rows spanning multiple raw `Date` values.
    If business_date is given, rows are filtered to raw Date == business_date
    BEFORE aggregation, so Country/app/etc breakdowns and the WW total are
    computed from the same filtered set and stay consistent with each other.
    """
    all_rows, resolved = await _get_app_downloads_rows_internal(
        client, app_id, report_date, granularity, detailed, access_type
    )

    distinct_raw_dates = sorted({row.get("date") for row in all_rows if row.get("date")})

    if business_date is not None:
        rows = [row for row in all_rows if row.get("date") == business_date]
    else:
        rows = all_rows

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
    breakdown_sum = sum(item["counts"] for item in breakdown)

    result: dict[str, Any] = {
        "total_downloads": total_downloads,
        "breakdown": breakdown,
        "processing_date": resolved.processing_date,
        "instance_id": resolved.instance_id,
        "distinct_raw_dates_before_filter": distinct_raw_dates,
        "rows_before_filter": len(all_rows),
        "rows_after_filter": len(rows),
        "breakdown_sum_matches_total": breakdown_sum == total_downloads,
    }

    if business_date is not None:
        result["business_date"] = business_date
        if len(rows) == 0:
            result["natural_empty"] = True
            result["note"] = (
                f"No rows with raw Date={business_date} found in this instance "
                f"(processing_date={resolved.processing_date}, "
                f"distinct raw dates present: {distinct_raw_dates}). "
                "total_downloads=0 reflects a proven absence, not a cross-date total."
            )

    return result
