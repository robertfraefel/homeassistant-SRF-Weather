"""Constants for the SRF Weather integration."""

DOMAIN = "srf_weather"

BASE_URL = "https://api.srgssr.ch/srf-meteo/v2"
TOKEN_URL = "https://api.srgssr.ch/oauth/v1/accesstoken"

DEFAULT_SCAN_INTERVAL = 1800  # 30 minutes

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"

PLATFORMS = ["weather", "sensor"]

# SRF symbol code → Home Assistant condition mapping.
# Codes 1-24 are daytime codes; 25-40 are night/variant codes.
# Source: SRF Meteo / MeteoSwiss symbol convention (approximate).
SYMBOL_TO_CONDITION: dict[int, str] = {
    1: "sunny",
    2: "sunny",
    3: "partlycloudy",
    4: "cloudy",
    5: "cloudy",
    6: "fog",
    7: "rainy",
    8: "rainy",
    9: "pouring",
    10: "lightning-rainy",
    11: "snowy",
    12: "snowy",
    13: "snowy-rainy",
    14: "snowy-rainy",
    15: "partlycloudy",
    16: "rainy",
    17: "lightning-rainy",
    18: "snowy",
    19: "snowy-rainy",
    20: "rainy",
    21: "pouring",
    22: "lightning-rainy",
    23: "snowy",
    24: "snowy-rainy",
    25: "clear-night",
    26: "partlycloudy",
    27: "fog",
    28: "rainy",
    29: "lightning-rainy",
    30: "snowy",
    31: "clear-night",
    32: "partlycloudy",
    33: "rainy",
    34: "lightning-rainy",
    35: "snowy",
    36: "snowy-rainy",
    37: "hail",
    38: "windy",
    39: "windy-variant",
    40: "exceptional",
}
