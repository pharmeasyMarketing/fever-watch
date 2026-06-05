"""Provider registry. Add a new source here and it's instantly selectable
by name from the CLI / WEATHER_PROVIDER env var."""
from __future__ import annotations

from .base import DailyWeather, WeatherProvider
from .nasa_power import NasaPowerProvider
from .open_meteo import OpenMeteoProvider

# NASA POWER is the DEFAULT: U.S. public-domain (CC0), no key, and no
# commercial/non-commercial licensing complications. Open-Meteo stays available
# behind the same interface as a dev/forecast option, but its free tier is
# non-commercial so it is deliberately not the default here.
_REGISTRY = {
    NasaPowerProvider.name: NasaPowerProvider,
    OpenMeteoProvider.name: OpenMeteoProvider,
}

DEFAULT_PROVIDER = NasaPowerProvider.name


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
