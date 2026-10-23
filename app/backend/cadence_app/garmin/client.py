from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
# Garmin documents 24-hour access tokens; renew early so long backfills never straddle expiry.
TOKEN_MAX_AGE_S = 23 * 3600
MAX_RETRY_AFTER_S = 300


class GarminError(Exception):
    pass


class RateLimited(GarminError):
    pass


class AuthError(GarminError):
    pass


class ServerError(GarminError):
    pass


@dataclass(frozen=True)
class Fetched:
    status: int
    content_type: str | None
    body: bytes


class GarminClient:
    def __init__(
        self,
        key: str,
        transport: httpx.BaseTransport | None = None,
        min_interval_s: float = 1.0,
        max_retries: int = 4,
        max_server_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        if not key.strip():
            raise GarminError("No Garmin credential is configured")
        self._key = key
        self._http = httpx.Client(
            base_url=BASE_URL, timeout=60, follow_redirects=False, transport=transport
        )
        self._token: str | None = None
        self._token_at = 0.0
        self._last_request = float("-inf")
        self._min_interval = min_interval_s
        self._max_retries = max_retries
        self._max_server_retries = max_server_retries
        self._sleep = sleep
        self._monotonic = monotonic
        self.requests_made = 0

    def close(self) -> None:
        self._http.close()

    def _throttle(self) -> None:
        wait = self._last_request + self._min_interval - self._monotonic()
        if wait > 0:
            self._sleep(wait)
        self._last_request = self._monotonic()
        self.requests_made += 1

    def authenticate(self) -> None:
        self._throttle()
        try:
            response = self._http.post(TOKEN_PATH, headers={"Authorization": f"ApiKey {self._key}"})
        except httpx.HTTPError:
            raise GarminError("Garmin authentication could not be reached") from None
        if response.status_code == 429:
            raise RateLimited("Garmin rate-limited authentication")
        if response.status_code != 200:
            raise AuthError(f"Garmin authentication returned HTTP {response.status_code}")
        token = _parse_token(response)
        if token is None:
            raise AuthError("Garmin authentication returned an unexpected format")
        self._token = token
        self._token_at = self._monotonic()

    def fetch(self, path: str, params: dict | None = None) -> Fetched:
        """GET with retries. Returns any non-retryable response for the caller to classify."""
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Only relative Garmin resource paths are allowed")
        reauthed = False
        attempt = 0
        while True:
            if self._token is None or self._monotonic() - self._token_at > TOKEN_MAX_AGE_S:
                self.authenticate()
            self._throttle()
            try:
                response = self._http.get(
                    path, params=params, headers={"Authorization": f"Bearer {self._token}"}
                )
            except httpx.HTTPError:
                response = None

            if response is not None and response.status_code == 401 and not reauthed:
                reauthed = True
                self._token = None
                continue
            if response is not None and response.status_code == 401:
                raise AuthError("Garmin rejected the access token (HTTP 401)")

            retryable = response is None or response.status_code == 429 or response.status_code >= 500
            if not retryable:
                return Fetched(
                    response.status_code,
                    response.headers.get("content-type"),
                    response.content,
                )
            limit = self._max_server_retries if response is not None and response.status_code >= 500 else self._max_retries
            if attempt >= limit:
                if response is not None and response.status_code == 429:
                    raise RateLimited("Garmin is rate-limiting requests; sync paused")
                if response is not None:
                    raise ServerError(f"Garmin request failed after retries (HTTP {response.status_code})")
                raise GarminError("Garmin request failed after retries (network error)")
            self._sleep(_backoff(response, attempt))
            attempt += 1


def _backoff(response: httpx.Response | None, attempt: int) -> float:
    if response is not None and response.status_code == 429:
        retry_after = response.headers.get("retry-after", "")
        if retry_after.isdigit():
            return min(float(retry_after), MAX_RETRY_AFTER_S)
        return min(15.0 * 2**attempt, MAX_RETRY_AFTER_S)
    return 2.0 * 2**attempt


def _parse_token(response: httpx.Response) -> str | None:
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            payload = response.json()
        except ValueError:
            return None
        token = payload.get("access_token") if isinstance(payload, dict) else None
    else:
        token = response.text.strip()
    if not isinstance(token, str) or len(token.split(".")) != 3 or any(c.isspace() for c in token):
        return None
    return token
