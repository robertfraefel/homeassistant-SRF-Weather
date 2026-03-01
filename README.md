# SRF Weather – Home Assistant Integration

A custom Home Assistant integration that fetches weather forecasts from the **SRF Meteo API** (SRG SSR) for any location in Switzerland.

## Features

- **Weather entity** with current conditions, daily forecast and hourly forecast
- **Extra sensor entities** for:
  - Felt temperature
  - Dew point
  - Sunshine duration (current hour, in minutes)
  - Sunshine hours (daily total)
  - Solar irradiance (W/m²)
  - Fresh snow (mm)
  - UV index
  - Precipitation probability
- Automatic OAuth2 token management (client credentials flow)
- Data refresh every 30 minutes
- German and English UI translations

## Requirements

- Home Assistant 2024.1 or newer
- An SRG SSR Developer account with access to the **SRF Meteo** product
  → Register at <https://developer.srgssr.ch>

## Installation

### HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/robertfraefel/homeassistant-SRF-Weather` as type **Integration**
3. Install **SRF Weather** and restart Home Assistant

### Manual

1. Copy the `custom_components/srf_weather` folder into your `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **SRF Weather**
3. Enter:
   - **Name** – display name for the weather entity
   - **Client ID** – from your SRG SSR developer app
   - **Client Secret** – from your SRG SSR developer app
   - **Latitude / Longitude** – coordinates of your location (defaults to your HA home location)

## API Reference

The integration uses the [SRF Meteo v2 API](https://developer.srgssr.ch):

| Endpoint | Description |
|---|---|
| `POST /oauth/v1/accesstoken` | OAuth2 client credentials token |
| `GET /srf-meteo/v2/forecastpoint/{lat},{lon}` | Weekly forecast (days, 3 h, 1 h) |

## Symbol Code Mapping

SRF uses numeric weather symbol codes (`symbol_code` / `symbol24_code`).
These are mapped to standard Home Assistant conditions (`sunny`, `partlycloudy`, `rainy`, …).
See `const.py` for the full mapping table.

## License

MIT
