"""App Store Downloads (Analytics Reports) tool."""

import hashlib
from typing import Any

from ..analytics_report_source import ResolvedSegments, resolve_app_downloads_segments
from ..cache import ReportCache
from ..client import ApiClient
from ..parsers import parse_app_downloads_report

_cache = ReportCache()

# Apple's raw "Download Type" values, keyed by their business meaning per R58.
# Matching is done on a normalized (lowercased, alnum-only) form so casing/
# hyphenation variants in the raw TSV (e.g. "First-Time Download") still match.
VALID_DOWNLOAD_TYPES = ["First-time download", "Redownload", "Restore", "Auto-update"]


def _normalize_download_type(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


_NORMALIZED_VALID_DOWNLOAD_TYPES = {_normalize_download_type(v) for v in VALID_DOWNLOAD_TYPES}


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
) -> tuple[list[dict[str, Any]], ResolvedSegments, str]:
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
    hasher = hashlib.sha256()
    for url in resolved.urls:
        raw = await client.fetch_analytics_segment(url)
        hasher.update(raw.encode("utf-8"))
        rows.extend(parse_app_downloads_report(raw))
    source_segment_sha256 = hasher.hexdigest()

    result = (rows, resolved, source_segment_sha256)
    _cache.set(cache_key, result)
    return result


class InvalidDownloadTypeError(ValueError):
    """Raised when download_type isn't one of Apple's supported values."""


async def get_app_downloads_report(
    client: ApiClient,
    app_id: str,
    report_date: str,
    group_by: str = "download_type",
    granularity: str = "DAILY",
    detailed: bool = True,
    access_type: str = "ONGOING",
    business_date: str | None = None,
    download_type: str | None = None,
) -> dict[str, Any]:
    """Get App Store Downloads, optionally filtered to a single raw business_date
    and/or a single raw download_type.

    report_date selects the Apple analyticsReportInstance (by processingDate);
    an instance can still contain rows spanning multiple raw `Date` values.
    Filters are applied, in order, BEFORE aggregation: business_date first,
    then download_type - so Country/app/etc breakdowns and the WW total are
    always computed from the same filtered row set and stay consistent with
    each other (no post-hoc proportional splitting).
    """
    if download_type is not None and _normalize_download_type(download_type) not in _NORMALIZED_VALID_DOWNLOAD_TYPES:
        raise InvalidDownloadTypeError(
            f"INVALID_DOWNLOAD_TYPE: '{download_type}' is not supported. "
            f"Supported values: {VALID_DOWNLOAD_TYPES}."
        )

    all_rows, resolved, source_segment_sha256 = await _get_app_downloads_rows_internal(
        client, app_id, report_date, granularity, detailed, access_type
    )

    distinct_raw_dates = sorted({row.get("date") for row in all_rows if row.get("date")})

    if business_date is not None:
        rows_after_business_date_filter = [row for row in all_rows if row.get("date") == business_date]
    else:
        rows_after_business_date_filter = all_rows

    if download_type is not None:
        normalized_target = _normalize_download_type(download_type)
        rows = [
            row
            for row in rows_after_business_date_filter
            if _normalize_download_type(row.get("download_type") or "") == normalized_target
        ]
    else:
        rows = rows_after_business_date_filter

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
        "app_id": app_id,
        "report_id": resolved.report_id,
        "total_downloads": total_downloads,
        "breakdown": breakdown,
        "processing_date": resolved.processing_date,
        "instance_id": resolved.instance_id,
        "distinct_raw_dates_before_filter": distinct_raw_dates,
        "rows_before_filter": len(all_rows),
        "rows_after_business_date_filter": len(rows_after_business_date_filter),
        "rows_after_download_type_filter": len(rows),
        "rows_after_filter": len(rows),
        "breakdown_sum_matches_total": breakdown_sum == total_downloads,
        "source_segment_sha256": source_segment_sha256,
    }

    if business_date is not None:
        result["business_date"] = business_date
    if download_type is not None:
        result["download_type"] = download_type

    if len(rows) == 0 and (business_date is not None or download_type is not None):
        result["natural_empty"] = True
        note_parts = []
        if business_date is not None:
            note_parts.append(f"raw Date={business_date}")
        if download_type is not None:
            note_parts.append(f"raw Download Type={download_type}")
        result["note"] = (
            f"No rows with {' and '.join(note_parts)} found in this instance "
            f"(processing_date={resolved.processing_date}, "
            f"distinct raw dates present: {distinct_raw_dates}). "
            "total_downloads=0 reflects a proven absence, not an unfiltered total."
        )

    return result
