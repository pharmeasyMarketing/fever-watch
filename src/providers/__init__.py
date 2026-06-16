"""Provider registry. Add a new source here and it's instantly selectable
by name from the CLI / WEATHER_PROVIDER env var."""
from __future__ import annotations

from .base import DailyWeather, WeatherProvider
from .cpc import CpcProvider
from .nasa_power import NasaPowerProvider
from .open_meteo import OpenMeteoProvider

# CPC is the DEFAULT: a hybrid that takes RAINFALL from NOAA CPC (gauge-based,
# US public domain; tracks Indian gauge truth far better than NASA's reanalysis
# rain) and TEMPERATURE + HUMIDITY from NASA POWER. Both are public domain, no
# key, commercial-OK. Revert to all-NASA at any time with --provider nasa-power
# (or WEATHER_PROVIDER=nasa-power). Open-Meteo stays available as a dev/forecast
# option, but its free tier is non-commercial so it is not a default here.
_REGISTRY = {
    CpcProvider.name: CpcProvider,
    NasaPowerProvider.name: NasaPowerProvider,
    OpenMeteoProvider.name: OpenMeteoProvider,
}

DEFAULT_PROVIDER = CpcProvider.name


def available() -> list[str]:
    return sorted(_REGISTRY)


def get_provider(name: str) -> WeatherProvider:
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise SystemExit(
            f"Unknown provider '{name}'. Available: {', '.join(available())}"
        )


__all__ = ["DailyWeather", "WeatherProvider", "get_provider", "available", "DEFAULT_PROVIDER"]
