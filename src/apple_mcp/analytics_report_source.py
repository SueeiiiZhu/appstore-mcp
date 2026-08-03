"""Resolve segment download URLs for Apple's Analytics Reports API.

Handles the multi-step Analytics Reports flow used by reports such as
"App Store Downloads" / "App Store Downloads Detailed":

1. Ensure an ONGOING analyticsReportRequest exists for the app.
2. Find the analyticsReport with the desired name (Standard vs Detailed).
3. Find the analyticsReportInstance matching the requested date/granularity.
4. List analyticsReportSegments to get pre-signed download URLs.
"""

import asyncio

from .client import ApiClient, ApiError

_APP_STORE_DOWNLOADS_STANDARD_NAME = "App Store Downloads"
_APP_STORE_DOWNLOADS_DETAILED_NAME = "App Store Downloads Detailed"

_POLL_BACKOFF_SECONDS = (5, 10, 20)


class AnalyticsReportNotReadyError(Exception):
    """Raised when no matching analytics report instance is available yet."""


async def ensure_ongoing_report_request(client: ApiClient, app_id: str) -> str:
    """Return the id of an ONGOING analyticsReportRequest for the app, creating one if needed."""
    existing_id = await _find_ongoing_report_request_id(client, app_id)
    if existing_id is not None:
        return existing_id

    try:
        created = await client.create_analytics_report_request(app_id, access_type="ONGOING")
    except ApiError as e:
        if e.status_code == 409:
            # Someone else created it concurrently (or it already existed) - re-list.
            existing_id = await _find_ongoing_report_request_id(client, app_id)
            if existing_id is not None:
                return existing_id
            raise
        raise

    request_id = created.get("data", {}).get("id")
    if not request_id:
        # Fall back to re-listing in case the create response was unexpectedly shaped.
        existing_id = await _find_ongoing_report_request_id(client, app_id)
        if existing_id is not None:
            return existing_id
        raise AnalyticsReportNotReadyError(
            "Failed to create or locate an ONGOING analyticsReportRequest for this app."
        )
    return request_id


async def _find_ongoing_report_request_id(client: ApiClient, app_id: str) -> str | None:
    listing = await client.list_analytics_report_requests(app_id)
    for item in listing.get("data", []):
        attributes = item.get("attributes", {})
        if attributes.get("accessType") == "ONGOING":
            return item.get("id")
    return None


async def resolve_app_downloads_segment_urls(
    client: ApiClient,
    app_id: str,
    report_date: str,
    granularity: str = "DAILY",
    detailed: bool = True,
    max_wait_seconds: int = 0,
) -> list[str]:
    """Resolve pre-signed segment download URLs for the App Store Downloads report.

    Raises AnalyticsReportNotReadyError if no report instance matches
    report_date and max_wait_seconds is 0 (or polling is exhausted).
    """
    report_request_id = await ensure_ongoing_report_request(client, app_id)
    report_name = (
        _APP_STORE_DOWNLOADS_DETAILED_NAME if detailed else _APP_STORE_DOWNLOADS_STANDARD_NAME
    )

    report_id = await _find_report_id(client, report_request_id, report_name)
    if report_id is None:
        raise AnalyticsReportNotReadyError(
            f"Report '{report_name}' is not available for this app yet. "
            "Analytics report data is typically ready at T+2 days; confirm the app has "
            "sufficient traffic and that the ONGOING report request has had time to populate "
            "(this can take up to 48 hours after first being created)."
        )

    remaining_wait = max(0, max_wait_seconds)
    delays = list(_POLL_BACKOFF_SECONDS)

    while True:
        instance_id = await _find_instance_id(client, report_id, granularity, report_date)
        if instance_id is not None:
            break

        if remaining_wait <= 0 or not delays:
            raise AnalyticsReportNotReadyError(
                f"No '{report_name}' report instance found for report_date={report_date} "
                f"granularity={granularity}. Analytics data is typically generated at T+2 days "
                "- confirm report_date is not too recent (or too old; data is generally "
                "retrievable back to 2024-01-01)."
            )

        delay = min(delays.pop(0), remaining_wait)
        await asyncio.sleep(delay)
        remaining_wait -= delay

    segments = await client.list_report_segments(instance_id)
    urls = [
        item.get("attributes", {}).get("url")
        for item in segments.get("data", [])
        if item.get("attributes", {}).get("url")
    ]
    if not urls:
        raise AnalyticsReportNotReadyError(
            f"Report instance {instance_id} has no downloadable segments yet."
        )
    return urls


async def _find_report_id(client: ApiClient, report_request_id: str, report_name: str) -> str | None:
    # filter[name] is passed server-side, but we still verify the name locally in case
    # the API ignores the filter and returns the full unfiltered list.
    listing = await client.list_analytics_reports(report_request_id, name=report_name)
    for item in listing.get("data", []):
        if item.get("attributes", {}).get("name") == report_name:
            return item.get("id")
    return None


async def _find_instance_id(
    client: ApiClient, report_id: str, granularity: str, report_date: str
) -> str | None:
    listing = await client.list_report_instances(report_id, granularity=granularity, processing_date=report_date)
    candidates = listing.get("data", [])

    # Prefer exact processingDate match if the server didn't already filter for us.
    for item in candidates:
        if item.get("attributes", {}).get("processingDate") == report_date:
            return item.get("id")

    # If the server-side filter[processingDate] was honored, any single result is fine.
    if len(candidates) == 1:
        return candidates[0].get("id")

    return None
