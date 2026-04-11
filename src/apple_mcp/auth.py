"""JWT token generation for App Store Connect API."""

import time

import jwt

_cached_token: dict | None = None
_cached_private_key: str | None = None


def _load_private_key(path: str) -> str:
    global _cached_private_key
    if _cached_private_key is None:
        with open(path) as f:
            _cached_private_key = f.read()
    return _cached_private_key


def generate_token(issuer_id: str, key_id: str, private_key_path: str) -> str:
    """Generate a JWT token for App Store Connect API.

    Caches the token and reuses it until 2 minutes before expiry.
    """
    global _cached_token
    now = int(time.time())

    if _cached_token and _cached_token["expires_at"] - now > 120:
        return _cached_token["token"]

    private_key = _load_private_key(private_key_path)
    expires_at = now + 15 * 60  # 15 minutes

    payload = {
        "iss": issuer_id,
        "iat": now,
        "exp": expires_at,
        "aud": "appstoreconnect-v1",
    }

    token = jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": key_id},
    )

    _cached_token = {"token": token, "expires_at": expires_at}
    return token


def clear_token_cache() -> None:
    global _cached_token, _cached_private_key
    _cached_token = None
    _cached_private_key = None
