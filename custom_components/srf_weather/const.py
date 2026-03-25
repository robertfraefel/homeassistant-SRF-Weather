"""Constants for the SRF Weather integration.

This module is imported by every other module in the integration, keeping all
magic strings and numbers in one place.

Symbol code mapping
-------------------
The SRF Meteo API returns a numeric ``symbol_code`` for each forecast interval.
Positive codes (1–30) represent daytime conditions; negative codes (-1 to -30)
are their night-time equivalents.  The icon SVGs confirm two structural groups:

  - Codes  1–16:  sun visible (partly cloudy base) — codes 3–9 show less
    cloud, codes 10–16 repeat the same precipitation pattern with more cloud.
  - Codes 17–30:  cloud-only / overcast — fog (17), plain cloud (18-19),
    and precipitation variants (20–30).

The ``SYMBOL_TO_CONDITION`` dict maps each positive code to a standard Home
Assistant weather condition string.  ``map_symbol_code()`` additionally handles
negative (night) codes by looking up ``abs(code)`` and converting ``"sunny"``
to ``"clear-night"``.
"""

# -------------------------------------------------------------------------
# Integration identity
# -------------------------------------------------------------------------

# Domain used as the key in hass.data and as the unique integration identifier
# in manifest.json.  Must match the folder name ``custom_components/srf_weather``.
DOMAIN = "srf_weather"

# -------------------------------------------------------------------------
# API endpoints
# -------------------------------------------------------------------------

# Base URL for all SRF Meteo v2 REST resources.
BASE_URL = "https://api.srgssr.ch/srf-meteo/v2"

# OAuth2 token endpoint.  The grant type is supplied as a query parameter
# rather than in the POST body, as required by the SRG SSR developer portal.
TOKEN_URL = "https://api.srgssr.ch/oauth/v1/accesstoken"

# -------------------------------------------------------------------------
# Polling
# -------------------------------------------------------------------------

# How often (in seconds) the coordinator refreshes forecast data.
# SRF Meteo updates its model output roughly every hour, so 30 minutes gives
# reasonably fresh data while staying well within API rate limits.
DEFAULT_SCAN_INTERVAL = 1800  # 30 minutes

# -------------------------------------------------------------------------
# Config entry keys
# -------------------------------------------------------------------------

# Keys used in the config entry ``data`` dict (set by the config flow).
# Standard HA constants cover CONF_LATITUDE, CONF_LONGITUDE, and CONF_NAME;
# the two below are integration-specific.
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_MAX_REQUESTS = "max_requests"
DEFAULT_MAX_REQUESTS = 40

# -------------------------------------------------------------------------
# Platforms
# -------------------------------------------------------------------------

# List of HA platform strings this integration registers entities for.
PLATFORMS = ["weather", "sensor"]

# -------------------------------------------------------------------------
# Symbol code → HA weather condition mapping
# -------------------------------------------------------------------------

# Home Assistant recognises the following condition strings:
#   clear-night, cloudy, exceptional, fog, hail, lightning, lightning-rainy,
#   partlycloudy, pouring, rainy, snowy, snowy-rainy, sunny, windy,
#   windy-variant
#
# Mapping derived from the official SRF Meteo API documentation (PDF) and
# verified against the SVG icon set (visual elements: sun, cloud, rain lines,
# lightning bolts, snow circles).  Only codes 1–30 exist; night-time is
# expressed via negative codes, NOT via codes 31–40.
SYMBOL_TO_CONDITION: dict[int, str] = {
    # --- Sun visible, less cloud (1–9) ---
    1:  "sunny",            # sonnig – clear sky, full sun
    2:  "fog",              # Nebelbänke – sun above fog/haze bands
    3:  "partlycloudy",     # teils sonnig – partly sunny, small cloud
    4:  "rainy",            # Regenschauer – rain showers (sun + cloud + rain)
    5:  "lightning-rainy",  # Gewitter mit Regen – thunderstorm with rain
    6:  "snowy",            # Schneeschauer – snow showers (sun + cloud + snow)
    7:  "hail",             # Gewitter mit Hagel – thunderstorm with hail
    8:  "snowy-rainy",      # Schneeregenschauer – sleet showers (rain + snow)
    9:  "lightning-rainy",  # Gewitter mit Schneeregen – thunderstorm with sleet
    # --- Sun visible, more cloud (10–16) – same precipitation pattern ---
    10: "partlycloudy",     # ziemlich sonnig – fairly sunny, larger cloud
    11: "rainy",            # Regenschauer – rain showers (more cloud)
    12: "lightning-rainy",  # Gewitter mit Regen – thunderstorm with rain
    13: "snowy",            # Schneeschauer – snow showers (more cloud)
    14: "hail",             # Gewitter mit Hagel – thunderstorm with hail
    15: "snowy-rainy",      # Schneeregenschauer – sleet showers
    16: "lightning-rainy",  # Gewitter mit Schneeregen – thunderstorm with sleet
    # --- Cloud-only / overcast (17–30) ---
    17: "fog",              # Nebel – fog (no cloud shape, just haze lines)
    18: "cloudy",           # bewölkt – cloudy
    19: "cloudy",           # bedeckt – overcast
    20: "rainy",            # regnerisch – rain (cloud + rain)
    21: "snowy",            # Schneefall – snowfall (cloud + snow)
    22: "snowy-rainy",      # Schneeregen – sleet (cloud + rain + snow)
    23: "pouring",          # starker Regen – heavy rain (cloud + lots of rain)
    24: "snowy",            # starker Schneefall – heavy snowfall
    25: "rainy",            # Regenschauer – rain showers (identical to 20)
    26: "lightning-rainy",  # Gewitter mit Regen – thunderstorm with rain
    27: "snowy",            # Schneefall – snowfall (identical to 21)
    28: "hail",             # Gewitter mit Hagel – thunderstorm with hail
    29: "snowy-rainy",      # Schneeregen – sleet (identical to 22)
    30: "lightning-rainy",  # Gewitter mit Schneeregen – thunderstorm with sleet
}


def map_symbol_code(symbol: int | None) -> str | None:
    """Map a symbol_code (positive or negative) to a HA condition string.

    The SRF API uses negative codes for night-time conditions, where ``-N``
    is the night variant of daytime code ``N``.  For codes that would map to
    ``"sunny"`` during the day, the night equivalent ``"clear-night"`` is
    returned instead.
    """
    if symbol is None:
        return None
    if symbol >= 0:
        return SYMBOL_TO_CONDITION.get(symbol)
    # Negative code → night variant of abs(symbol)
    condition = SYMBOL_TO_CONDITION.get(abs(symbol))
    if condition == "sunny":
        return "clear-night"
    return condition
