"""Resolve segment download URLs for Apple's Analytics Reports API.

Handles the multi-step Analytics Reports flow used by reports such as
"App Downloads" (Standard / Detailed):

1. Ensure an analyticsReportRequest exists for the app, either ONGOING
   (subscribes going forward, data starts ~24-48h after creation) or
   ONE_TIME_SNAPSHOT (one-off historical pull, as far back as Apple has
   data available at request-creation time - no new data after that).
2. Find the analyticsReport with the desired name (Standard vs Detailed).
3. Find the analyticsReportInstance matching the requested date/granularity.
4. List analyticsReportSegments to get pre-signed download URLs.
"""

import asyncio

from .client import ApiClient, ApiError

# Apple's exact `attributes.name` strings for report variants aren't reliably
# documented (and filter[name] server-side filtering isn't confirmed either),
# so reports are matched locally by substring: name contains "App Downloads"
# (confirmed via live API response to be e.g. "App Downloads Standard" /
# "App Downloads Detailed" - no "Store" or "Report" in the name), and
# "Detailed" presence/absence picks the variant.
_APP_DOWNLOADS_NAME_FRAGMENT = "app downloads"
_DETAILED_FRAGMENT = "detailed"

_POLL_BACKOFF_SECONDS = (5, 10, 20)


class AnalyticsReportNotReadyError(Exception):
    """Raised when no matching analytics report instance is available yet."""


async def ensure_ongoing_report_request(client: ApiClient, app_id: str) -> str:
    """Return the id of an ONGOING analyticsReportRequest for the app, creating one if needed."""
    return await ensure_report_request(client, app_id, access_type="ONGOING")


async def ensure_report_request(client: ApiClient, app_id: str, access_type: str = "ONGOING") -> str:
    """Return the id of an analyticsReportRequest with the given access_type, creating one if needed.

    access_type is either "ONGOING" (subscribes going forward) or
    "ONE_TIME_SNAPSHOT" (one-off historical pull). Apple appears to allow only
    one request per accessType per app at a time; a 409 on create is treated
    as "already exists" and resolved by re-listing.
    """
    existing_id = await _find_report_request_id(client, app_id, access_type)
    if existing_id is not None:
        return existing_id

    try:
        created = await client.create_analytics_report_request(app_id, access_type=access_type)
    except ApiError as e:
        if e.status_code == 409:
            # Someone else created it concurrently (or it already existed) - re-list.
            existing_id = await _find_report_request_id(client, app_id, access_type)
            if existing_id is not None:
                return existing_id
            raise
        raise

    request_id = created.get("data", {}).get("id")
    if not request_id:
        # Fall back to re-listing in case the create response was unexpectedly shaped.
        existing_id = await _find_report_request_id(client, app_id, access_type)
        if existing_id is not None:
            return existing_id
        raise AnalyticsReportNotReadyError(
            f"Failed to create or locate a {access_type} analyticsReportRequest for this app."
        )
    return request_id


async def _find_report_request_id(client: ApiClient, app_id: str, access_type: str) -> str | None:
    listing = await client.list_analytics_report_requests(app_id, access_type=access_type)
    for item in listing.get("data", []):
        attributes = item.get("attributes", {})
        if attributes.get("accessType") == access_type:
            return item.get("id")
    return None


async def resolve_app_downloads_segment_urls(
    client: ApiClient,
    app_id: str,
    report_date: str,
    granularity: str = "DAILY",
    detailed: bool = True,
    max_wait_seconds: int = 0,
    access_type: str = "ONGOING",
) -> list[str]:
    """Resolve pre-signed segment download URLs for the App Downloads report.

    access_type selects which analyticsReportRequest to use: "ONGOING" (data
    from ~24-48h after the request was first created, onward) or
    "ONE_TIME_SNAPSHOT" (a one-off historical pull, useful for dates further
    in the past than the ONGOING request's creation time).

    Raises AnalyticsReportNotReadyError if no report instance matches
    report_date and max_wait_seconds is 0 (or polling is exhausted).
    """
    report_request_id = await ensure_report_request(client, app_id, access_type=access_type)
    report_label = "App Downloads Detailed" if detailed else "App Downloads Standard"

    report_id = await _find_report_id(client, report_request_id, detailed=detailed)
    if report_id is None:
        raise AnalyticsReportNotReadyError(
            f"Report '{report_label}' is not available for this app yet. "
            f"Analytics report data is typically ready at T+2 days; confirm the app has "
            f"sufficient traffic and that the {access_type} report request has had time to "
            "populate (this can take up to 48 hours after first being created)."
        )

    remaining_wait = max(0, max_wait_seconds)
    delays = list(_POLL_BACKOFF_SECONDS)

    while True:
        instance_id = await _find_instance_id(client, report_id, granularity, report_date)
        if instance_id is not None:
            break

        if remaining_wait <= 0 or not delays:
            hint = (
                "Analytics data is typically generated at T+2 days - confirm report_date is not "
                "too recent."
                if access_type == "ONGOING"
                else "Apple generates ONE_TIME_SNAPSHOT instances asynchronously after the request "
                "is created; if this was just requested, wait and retry. Historical data is "
                "generally retrievable back to 2024-01-01."
            )
            access_type_hint = (
                f" Try access_type='ONE_TIME_SNAPSHOT' for dates before this app's ONGOING "
                "report request was first created."
                if access_type == "ONGOING"
                else ""
            )
            raise AnalyticsReportNotReadyError(
                f"No '{report_label}' report instance found for report_date={report_date} "
                f"granularity={granularity} access_type={access_type}. {hint}{access_type_hint}"
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


async def _find_report_id(client: ApiClient, report_request_id: str, detailed: bool) -> str | None:
    # Apple's exact `attributes.name` string isn't reliably documented, and
    # server-side filter[name] support isn't confirmed either, so this fetches
    # the full unfiltered list and matches locally by substring/case-insensitive.
    listing = await client.list_analytics_reports(report_request_id)
    for item in listing.get("data", []):
        name = (item.get("attributes", {}).get("name") or "").strip().lower()
        if _APP_DOWNLOADS_NAME_FRAGMENT not in name:
            continue
        is_detailed = _DETAILED_FRAGMENT in name
        if is_detailed == detailed:
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
