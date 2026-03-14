"""Async HTTP client for the SRF Meteo v2 API (SRG SSR).

Authentication
--------------
The API uses the OAuth2 *client credentials* flow:

1. ``POST https://api.srgssr.ch/oauth/v1/accesstoken?grant_type=client_credentials``
   with ``Authorization: Basic base64(client_id:client_secret)``
2. The response contains ``access_token`` and ``expires_in`` (seconds).
3. Every subsequent API call carries ``Authorization: Bearer <token>``.

The client caches the token in memory and refreshes it automatically 60 s
before it expires, avoiding the need for callers to manage token lifecycle.

Forecast endpoint
-----------------
``GET /srf-meteo/v2/forecastpoint/{geolocationId}``

The ``geolocationId`` is ``"{lat:.4f},{lon:.4f}"`` – latitude and longitude
rounded to four decimal places (e.g. ``"47.3769,8.5417"``).

The response is a ``ForecastPointWeek`` JSON object containing:
  - ``days``        – daily forecast intervals
  - ``three_hours`` – 3-hour forecast intervals (not used by this integration)
  - ``hours``       – 1-hour forecast intervals
  - ``geolocation`` – metadata about the resolved location
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timedelta

import aiohttp

from .const import BASE_URL, TOKEN_URL

_LOGGER = logging.getLogger(__name__)


class SRFWeatherAuthError(Exception):
    """Raised when the SRG SSR API rejects the client credentials.

    This typically means the ``client_id`` or ``client_secret`` is wrong,
    or the associated developer account has been disabled.
    """


class SRFWeatherAPIError(Exception):
    """Raised for unexpected API or network errors.

    Covers HTTP 4xx/5xx responses (other than auth errors) as well as
    low-level ``aiohttp.ClientError`` exceptions.
    """


class SRFWeatherRateLimitError(SRFWeatherAPIError):
    """Raised when the API returns HTTP 429 (quota exceeded).

    Callers should back off significantly to avoid wasting the remaining
    daily quota on futile retries.
    """


class SRFWeatherAPI:
    """Async client for the SRF Meteo v2 REST API.

    All methods are coroutines and must be awaited.  A single instance is
    created per config entry and shared by the coordinator for all fetches.

    Attributes:
        _client_id:      OAuth2 client ID from the SRG SSR developer portal.
        _client_secret:  Corresponding client secret.
        _session:        Shared ``aiohttp.ClientSession`` managed by HA.
        _token:          Cached bearer token, or ``None`` if not yet fetched.
        _token_expires:  ``datetime`` after which the cached token must be
                         refreshed, or ``None`` if no token has been fetched.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialise the API client.

        Args:
            client_id:     SRG SSR OAuth2 client ID.
            client_secret: SRG SSR OAuth2 client secret.
            session:       The ``aiohttp.ClientSession`` to use for all HTTP
                           requests.  Pass the HA-managed session obtained via
                           ``async_get_clientsession(hass)``.
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = session
        self._token: str | None = None
        self._token_expires: datetime | None = None
        self._geo_id_cache: dict[str, str] = {}
        self._geo_cache_file: str | None = None

    def set_storage_dir(self, config_dir: str) -> None:
        """Set the directory for persistent cache files.

        Args:
            config_dir: HA config directory (``hass.config.config_dir``).
        """
        self._geo_cache_file = os.path.join(config_dir, ".srf_weather_geo_cache.json")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_token(self) -> None:
        """Request a new OAuth2 access token from the SRG SSR token endpoint.

        Encodes ``client_id:client_secret`` as Base64 for the Basic
        Authorization header (as required by RFC 6749 §2.3.1).  On success
        the token and its calculated expiry time are written to instance
        attributes so that ``_get_token`` can serve cached values.

        Raises:
            SRFWeatherAuthError: HTTP 401 or 403 – credentials rejected.
            SRFWeatherAPIError:  Any other non-200 HTTP status or network
                                 failure (``aiohttp.ClientError``).
        """
        # Build Basic auth header: base64("client_id:client_secret")
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
                if resp.status == 429:
                    body = await resp.text()
                    raise SRFWeatherRateLimitError(
                        f"API quota exceeded (HTTP 429): {body}"
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

        # Schedule renewal 60 s before actual expiry to avoid a race where an
        # in-flight request uses a token that expires mid-request.
        self._token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
        _LOGGER.debug(
            "SRF Weather: new access token obtained, expires in %ss", expires_in
        )

    async def _get_token(self) -> str:
        """Return a valid bearer token, fetching a new one if needed.

        Checks the cached token's expiry time and refreshes proactively when
        it is about to expire.

        Returns:
            A valid OAuth2 bearer token string.

        Raises:
            SRFWeatherAuthError: Propagated from ``_fetch_token``.
            SRFWeatherAPIError:  Propagated from ``_fetch_token``.
        """
        if (
            self._token is None
            or self._token_expires is None
            or datetime.now() >= self._token_expires
        ):
            await self._fetch_token()
        return self._token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    async def _get_geolocation_id(self, lat: float, lon: float) -> str:
        """Look up the SRF geolocation ID for the given coordinates.

        Calls ``GET /srf-meteo/v2/geolocations?latitude={lat}&longitude={lon}``
        and returns the ``id`` of the first (nearest) result.  The result is
        cached so that subsequent forecast polls do not repeat the lookup.

        Raises:
            SRFWeatherAPIError: No geolocation found or network failure.
        """
        cache_key = f"{lat:.4f},{lon:.4f}"
        if cache_key in self._geo_id_cache:
            return self._geo_id_cache[cache_key]

        # Check persistent file cache
        if self._geo_cache_file:
            try:
                geo_id = await asyncio.to_thread(
                    self._read_geo_cache, cache_key
                )
                if geo_id is not None:
                    self._geo_id_cache[cache_key] = geo_id
                    _LOGGER.debug(
                        "SRF Weather: loaded geo ID from file cache: %s",
                        geo_id,
                    )
                    return geo_id
            except (OSError, json.JSONDecodeError, KeyError):
                pass  # file missing or corrupt - fall through to API

        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/geolocations"
        params = {"latitude": str(lat), "longitude": str(lon)}

        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (401, 403):
                    self._token = None
                    raise SRFWeatherAuthError(
                        f"Unauthorized fetching geolocations (HTTP {resp.status})"
                    )
                if resp.status == 429:
                    body = await resp.text()
                    raise SRFWeatherRateLimitError(
                        f"API quota exceeded (HTTP 429): {body}"
                    )
                if resp.status != 200:
                    body = await resp.text()
                    raise SRFWeatherAPIError(
                        f"Geolocation request failed (HTTP {resp.status}): {body}"
                    )
                data = await resp.json()
                if not data:
                    raise SRFWeatherAPIError(
                        f"No geolocation found for coordinates {lat},{lon}"
                    )
                # The API returns a list; pick the first (nearest) entry.
                geo_id = data[0]["id"]
                self._geo_id_cache[cache_key] = geo_id

                # Persist to file so we survive HA restarts
                if self._geo_cache_file:
                    try:
                        await asyncio.to_thread(
                            self._write_geo_cache, cache_key, geo_id
                        )
                    except OSError:
                        pass  # non-critical

                _LOGGER.debug(
                    "SRF Weather: resolved (%s, %s) -> geolocation ID %s",
                    lat, lon, geo_id,
                )
                return geo_id
        except aiohttp.ClientError as exc:
            raise SRFWeatherAPIError(
                f"Network error fetching geolocations: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Synchronous cache helpers (run via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _read_geo_cache(self, cache_key: str) -> str | None:
        """Read a geo ID from the persistent file cache (blocking)."""
        if self._geo_cache_file and os.path.exists(self._geo_cache_file):
            with open(self._geo_cache_file, "r") as fh:
                file_cache = json.load(fh)
            return file_cache.get(cache_key)
        return None

    def _write_geo_cache(self, cache_key: str, geo_id: str) -> None:
        """Write a geo ID to the persistent file cache (blocking)."""
        if not self._geo_cache_file:
            return
        file_cache: dict[str, str] = {}
        if os.path.exists(self._geo_cache_file):
            with open(self._geo_cache_file, "r") as fh:
                file_cache = json.load(fh)
        file_cache[cache_key] = geo_id
        with open(self._geo_cache_file, "w") as fh:
            json.dump(file_cache, fh)

    # Public API
    # ------------------------------------------------------------------

    async def get_forecast(self, lat: float, lon: float) -> dict:
        """Fetch the weekly forecast for the given coordinates.

        Calls ``GET /srf-meteo/v2/forecastpoint/{geolocationId}`` where
        ``geolocationId`` is ``"{lat:.4f},{lon:.4f}"``.

        The returned dictionary mirrors the ``ForecastPointWeek`` schema:

        .. code-block:: json

            {
              "days":        [ { "date_time": "...", "TX_C": 22, ... }, ... ],
              "three_hours": [ { "date_time": "...", "TTT_C": 18, ... }, ... ],
              "hours":       [ { "date_time": "...", "TTT_C": 17, ... }, ... ],
              "geolocation": { "id": "...", "lat": 47.3769, ... }
            }

        If the token has been revoked mid-session (HTTP 401/403), the cached
        token is cleared so the next call will re-authenticate automatically.

        Args:
            lat: Latitude of the forecast location (WGS-84 decimal degrees).
            lon: Longitude of the forecast location (WGS-84 decimal degrees).

        Returns:
            Parsed JSON response as a Python dictionary.

        Raises:
            SRFWeatherAuthError: Token was revoked or rejected by the API.
            SRFWeatherAPIError:  HTTP 404 (location not found), any other
                                 non-200 status, or a network failure.
        """
        # Look up the geolocation ID via the /geolocations endpoint.
        geo_id = await self._get_geolocation_id(lat, lon)
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
                    # Clear the cached token so the next coordinator poll will
                    # attempt to re-authenticate rather than replaying an
                    # invalid token indefinitely.
                    self._token = None
                    raise SRFWeatherAuthError(
                        f"Unauthorized fetching forecast (HTTP {resp.status})"
                    )
                if resp.status == 404:
                    raise SRFWeatherAPIError(
                        f"Location not found for coordinates {lat},{lon}"
                    )
                if resp.status == 429:
                    body = await resp.text()
                    raise SRFWeatherRateLimitError(
                        f"API quota exceeded (HTTP 429): {body}"
                    )
                if resp.status != 200:
                    body = await resp.text()
                    raise SRFWeatherAPIError(
                        f"Forecast request failed (HTTP {resp.status}): {body}"
                    )
                return await resp.json()
        except aiohttp.ClientError as exc:
            raise SRFWeatherAPIError(
                f"Network error fetching forecast: {exc}"
            ) from exc

    async def validate_credentials(self) -> bool:
        """Test whether the stored credentials can obtain a valid token.

        Used by the config flow to give the user immediate feedback if their
        Client ID or Secret is wrong, before creating a config entry.

        Returns:
            ``True`` if authentication succeeded, ``False`` otherwise.
        """
        try:
            await self._fetch_token()
            return True
        except (SRFWeatherAuthError, SRFWeatherAPIError):
            return False

