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

    async def close(self) -> None:
        await self._http.aclose()
