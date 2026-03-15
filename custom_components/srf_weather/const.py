"""Constants for the SRF Weather integration.

This module is imported by every other module in the integration, keeping all
magic strings and numbers in one place.

Symbol code mapping
-------------------
The SRF Meteo API returns a numeric ``symbol_code`` (and ``symbol24_code`` for
night representations) for each forecast interval.  These integers follow the
SRF / MeteoSwiss convention where:

  - Codes  1–24  represent *daytime* weather conditions.
  - Codes 25–40  represent *night-time* or variant conditions.

The ``SYMBOL_TO_CONDITION`` dict maps each code to one of the standard Home
Assistant weather condition strings.  Unknown codes fall back to ``None``
(HA treats ``None`` as "unknown").
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
# The SRF symbol codes below are based on the SRF Meteo / MeteoSwiss
# symbol convention.  Codes not listed here will map to ``None`` (unknown).
SYMBOL_TO_CONDITION: dict[int, str] = {
    # --- Daytime codes (1–24) ---
    1:  "sunny",            # Clear sky
    2:  "sunny",            # Mostly clear, isolated high clouds
    3:  "partlycloudy",     # Partly cloudy
    4:  "cloudy",           # Mostly cloudy
    5:  "cloudy",           # Overcast
    6:  "fog",              # Fog or low stratus
    7:  "rainy",            # Light rain / drizzle
    8:  "rainy",            # Moderate rain
    9:  "pouring",          # Heavy rain
    10: "lightning-rainy",  # Thunderstorm with rain
    11: "snowy",            # Light snowfall
    12: "snowy",            # Moderate to heavy snowfall
    13: "snowy-rainy",      # Sleet (mixed rain and snow)
    14: "snowy-rainy",      # Freezing rain / glaze ice
    15: "partlycloudy",     # Partly cloudy with high cirrus clouds
    16: "rainy",            # Partly cloudy with showers
    17: "lightning-rainy",  # Partly cloudy with thunderstorm shower
    18: "snowy",            # Partly cloudy with snow shower
    19: "snowy-rainy",      # Partly cloudy with sleet shower
    20: "rainy",            # Overcast with rain
    21: "pouring",          # Overcast with heavy rain
    22: "lightning-rainy",  # Overcast with thunderstorm
    23: "snowy",            # Overcast with snow
    24: "snowy-rainy",      # Overcast with sleet
    # --- Night-time / variant codes (25–40) ---
    25: "clear-night",      # Clear night sky
    26: "partlycloudy",     # Partly cloudy night
    27: "fog",              # Foggy night
    28: "rainy",            # Rainy night
    29: "lightning-rainy",  # Thunderstorm at night
    30: "snowy",            # Snowy night
    31: "clear-night",      # Mostly clear night
    32: "partlycloudy",     # Partly cloudy night (variant)
    33: "rainy",            # Night showers
    34: "lightning-rainy",  # Night thunderstorm showers
    35: "snowy",            # Night snow showers
    36: "snowy-rainy",      # Night sleet showers
    37: "hail",             # Hail
    38: "windy",            # Windy / blustery
    39: "windy-variant",    # Very windy / storm-force
    40: "exceptional",      # Extreme or exceptional weather event
}
