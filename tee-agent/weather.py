"""Weather check (§4.2): Open-Meteo primary (free, no key), NWS backup."""

import logging
from datetime import datetime

import requests

import config

logger = logging.getLogger(__name__)

# WMO weather codes for thunderstorms — any of these is an automatic trip.
THUNDERSTORM_CODES = {95, 96, 99}


def forecast_at(tee_time: datetime) -> dict | None:
    """Hourly forecast for Fargo at the tee time hour, or None if both
    providers fail (callers treat None as 'cannot evaluate', not 'all clear')."""
    try:
        return _open_meteo(tee_time)
    except Exception as e:
        logger.warning("Open-Meteo failed (%s), trying NWS", e)
    try:
        return _nws(tee_time)
    except Exception as e:
        logger.error("NWS backup also failed: %s", e)
        return None


def check(tee_time: datetime, thresholds: dict) -> list[str]:
    """Return human-readable trip reasons (empty list = weather OK)."""
    fc = forecast_at(tee_time)
    if fc is None:
        return []  # watchdog audits this separately; don't cancel on no-data
    reasons = []
    if fc["precip_probability"] > thresholds["precip_probability_max"]:
        reasons.append(f"Rain {fc['precip_probability']:.0f}%")
    if fc["wind_mph"] > thresholds["wind_mph_max"]:
        reasons.append(f"Wind {fc['wind_mph']:.0f} mph")
    if fc["temp_f"] < thresholds["temp_f_min"]:
        reasons.append(f"Temp {fc['temp_f']:.0f}°F")
    if fc.get("weather_code") in THUNDERSTORM_CODES:
        reasons.append("Thunderstorms forecast")
    return reasons


def _open_meteo(tee_time: datetime) -> dict:
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": config.FARGO_LAT,
            "longitude": config.FARGO_LON,
            "hourly": "temperature_2m,precipitation_probability,wind_speed_10m,weather_code",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": config.LOCAL_TZ,
            "start_date": tee_time.strftime("%Y-%m-%d"),
            "end_date": tee_time.strftime("%Y-%m-%d"),
        },
        timeout=10,
    )
    resp.raise_for_status()
    hourly = resp.json()["hourly"]
    idx = hourly["time"].index(tee_time.strftime("%Y-%m-%dT%H:00"))
    return {
        "temp_f": hourly["temperature_2m"][idx],
        "precip_probability": hourly["precipitation_probability"][idx],
        "wind_mph": hourly["wind_speed_10m"][idx],
        "weather_code": hourly["weather_code"][idx],
        "source": "open-meteo",
    }


def _nws(tee_time: datetime) -> dict:
    headers = {"User-Agent": "tee-agent (personal use)"}
    points = requests.get(
        f"https://api.weather.gov/points/{config.FARGO_LAT},{config.FARGO_LON}",
        headers=headers, timeout=10,
    )
    points.raise_for_status()
    hourly_url = points.json()["properties"]["forecastHourly"]
    fc = requests.get(hourly_url, headers=headers, timeout=10)
    fc.raise_for_status()
    target = tee_time.replace(minute=0, second=0, microsecond=0)
    for period in fc.json()["properties"]["periods"]:
        if datetime.fromisoformat(period["startTime"]).replace(tzinfo=None) == target.replace(tzinfo=None):
            return {
                "temp_f": period["temperature"],
                "precip_probability": (period.get("probabilityOfPrecipitation") or {}).get("value") or 0,
                "wind_mph": float(period["windSpeed"].split()[0]),
                # NWS uses text, not WMO codes; flag thunderstorms via keyword.
                "weather_code": 95 if "thunder" in period["shortForecast"].lower() else 0,
                "source": "nws",
            }
    raise ValueError(f"No NWS period matched {target}")
