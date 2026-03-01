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

import base64
import logging
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
        # The SRF API expects four decimal places of precision in the geo ID.
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
