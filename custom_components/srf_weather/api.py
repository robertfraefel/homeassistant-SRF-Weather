"""Async API client for SRF Weather (SRG SSR)."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta

import aiohttp

from .const import BASE_URL, TOKEN_URL

_LOGGER = logging.getLogger(__name__)


class SRFWeatherAuthError(Exception):
    """Raised when authentication fails."""


class SRFWeatherAPIError(Exception):
    """Raised when the API returns an unexpected error."""


class SRFWeatherAPI:
    """Client for the SRF Meteo v2 REST API.

    Authentication uses OAuth2 client credentials flow.  The token is cached
    and renewed automatically before it expires.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = session
        self._token: str | None = None
        self._token_expires: datetime | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_token(self) -> None:
        """Fetch a fresh OAuth2 access token and cache it."""
        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            async with self._session.post(
                TOKEN_URL,
                params={"grant_type": "client_credentials"},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (401, 403):
                    raise SRFWeatherAuthError(
                        f"Invalid credentials (HTTP {resp.status})"
                    )
                if resp.status != 200:
                    body = await resp.text()
                    raise SRFWeatherAPIError(
                        f"Token request failed (HTTP {resp.status}): {body}"
                    )
                data = await resp.json()
        except aiohttp.ClientError as exc:
            raise SRFWeatherAPIError(f"Network error fetching token: {exc}") from exc

        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        # Renew 60 s before actual expiry to avoid race conditions.
        self._token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
        _LOGGER.debug("SRF Weather: new access token obtained, expires in %ss", expires_in)

    async def _get_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if (
            self._token is None
            or self._token_expires is None
            or datetime.now() >= self._token_expires
        ):
            await self._fetch_token()
        return self._token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_forecast(self, lat: float, lon: float) -> dict:
        """Fetch the weekly forecast for the given coordinates.

        The geolocation ID expected by SRF is ``lat,lon`` rounded to 4
        decimal places (e.g. ``47.3769,8.5417``).
        """
        geo_id = f"{lat:.4f},{lon:.4f}"
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/forecastpoint/{geo_id}"

        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (401, 403):
                    # Token may have been revoked; clear cache and surface error.
                    self._token = None
                    raise SRFWeatherAuthError(
                        f"Unauthorized fetching forecast (HTTP {resp.status})"
                    )
                if resp.status == 404:
                    raise SRFWeatherAPIError(
                        f"Location not found for coordinates {lat},{lon}"
                    )
                if resp.status != 200:
                    body = await resp.text()
                    raise SRFWeatherAPIError(
                        f"Forecast request failed (HTTP {resp.status}): {body}"
                    )
                return await resp.json()
        except aiohttp.ClientError as exc:
            raise SRFWeatherAPIError(f"Network error fetching forecast: {exc}") from exc

    async def validate_credentials(self) -> bool:
        """Return True if the stored credentials yield a valid token."""
        try:
            await self._fetch_token()
            return True
        except (SRFWeatherAuthError, SRFWeatherAPIError):
            return False
