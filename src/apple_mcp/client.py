"""HTTP client for App Store Connect API."""

from dataclasses import dataclass, field

import httpx

from .auth import generate_token
from .parsers import decode_report_bytes

BASE_URL = "https://api.appstoreconnect.apple.com"


class ApiError(Exception):
    def __init__(self, status_code: int, body: str, path: str):
        self.status_code = status_code
        self.body = body
        self.path = path
        super().__init__(f"API error {status_code} on {path}: {body}")

    def to_user_message(self) -> str:
        match self.status_code:
            case 401 | 403:
                return "Authentication failed. Check your Issuer ID, Key ID, and .p8 key path."
            case 404:
                return "Report not found. It may not be available yet (daily reports are typically ready by 8 AM PST the next day)."
            case 429:
                return "Rate limited by Apple. Please wait a moment before retrying."
            case _:
                return f"Apple API error ({self.status_code}): {self.body}"


@dataclass
class ApiClient:
    issuer_id: str
    key_id: str
    private_key_path: str
    vendor_number: str
    _http: httpx.AsyncClient = field(default_factory=lambda: httpx.AsyncClient(timeout=60), init=False)

    def _auth_header(self) -> str:
        token = generate_token(self.issuer_id, self.key_id, self.private_key_path)
        return f"Bearer {token}"

    async def fetch_json(self, path: str, params: dict[str, str] | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        resp = await self._http.get(
            url,
            params=params,
            headers={"Authorization": self._auth_header(), "Accept": "application/json"},
        )
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, resp.text, path)
        return resp.json()

    async def fetch_gzipped_report(self, path: str, params: dict[str, str]) -> str:
        url = f"{BASE_URL}{path}"
        resp = await self._http.get(
            url,
            params=params,
            headers={"Authorization": self._auth_header(), "Accept": "application/a-gzip"},
        )
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, resp.text, path)
        return decode_report_bytes(resp.content)

    async def post_json(self, path: str, body: dict) -> dict:
        url = f"{BASE_URL}{path}"
        resp = await self._http.post(
            url,
            json=body,
            headers={
                "Authorization": self._auth_header(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, resp.text, path)
        if not resp.content:
            return {}
        return resp.json()

    async def create_analytics_report_request(self, app_id: str, access_type: str = "ONGOING") -> dict:
        body = {
            "data": {
                "type": "analyticsReportRequests",
                "attributes": {"accessType": access_type},
                "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
            }
        }
        return await self.post_json("/v1/analyticsReportRequests", body)

    async def list_analytics_report_requests(self, app_id: str) -> dict:
        return await self.fetch_json(
            f"/v1/apps/{app_id}/analyticsReportRequests",
            {"filter[accessType]": "ONGOING"},
        )

    async def list_analytics_reports(self, report_request_id: str, name: str | None = None) -> dict:
        params: dict[str, str] = {}
        if name is not None:
            params["filter[name]"] = name
        return await self.fetch_json(
            f"/v1/analyticsReportRequests/{report_request_id}/reports", params
        )

    async def list_report_instances(
        self,
        report_id: str,
        granularity: str = "DAILY",
        processing_date: str | None = None,
    ) -> dict:
        params: dict[str, str] = {"filter[granularity]": granularity}
        if processing_date is not None:
            params["filter[processingDate]"] = processing_date

        data = await self.fetch_json(f"/v1/analyticsReports/{report_id}/instances", params)
        all_data = list(data.get("data", []))

        next_url = data.get("links", {}).get("next")
        while next_url:
            page = await self._fetch_absolute_json(next_url)
            all_data.extend(page.get("data", []))
            next_url = page.get("links", {}).get("next")

        data["data"] = all_data
        return data

    async def list_report_segments(self, instance_id: str) -> dict:
        return await self.fetch_json(f"/v1/analyticsReportInstances/{instance_id}/segments")

    async def fetch_analytics_segment(self, url: str) -> str:
        """Download a pre-signed analytics report segment. No Authorization header is sent."""
        resp = await self._http.get(url, headers={"Accept": "application/a-gzip"})
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, resp.text, url)
        return decode_report_bytes(resp.content, url)

    async def _fetch_absolute_json(self, url: str) -> dict:
        resp = await self._http.get(
            url,
            headers={"Authorization": self._auth_header(), "Accept": "application/json"},
        )
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, resp.text, url)
        return resp.json()

    async def close(self) -> None:
        await self._http.aclose()
