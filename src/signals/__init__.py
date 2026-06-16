"""Signal-provider registries for trends (signal 2) and positivity (signal 3).

Mock is the default until the real feeds land; swap by name without touching the
grid builder, mirroring the weather providers/ registry.
"""
from __future__ import annotations

from typing import Optional

from .base import PositivityProvider, TrendsProvider
from .mock import MockPositivityProvider, MockTrendsProvider
from .googlesheet import GoogleSheetPositivityProvider
from .gsheet_api import GSheetApiPositivityProvider
from .cached import CachedTrendsProvider

_TRENDS = {MockTrendsProvider.name: MockTrendsProvider}
_POSITIVITY = {
    MockPositivityProvider.name: MockPositivityProvider,
    GoogleSheetPositivityProvider.name: GoogleSheetPositivityProvider,
    GSheetApiPositivityProvider.name: GSheetApiPositivityProvider,
}

DEFAULT_TRENDS = MockTrendsProvider.name
DEFAULT_POSITIVITY = MockPositivityProvider.name


def trends_available() -> list[str]:
    return sorted(_TRENDS)


def positivity_available() -> list[str]:
    return sorted(_POSITIVITY)


def get_trends_provider(name: Optional[str] = None, config: Optional[dict] = None) -> TrendsProvider:
    key = name or DEFAULT_TRENDS
    cfg = config or {}
    if key == MockTrendsProvider.name:
        return MockTrendsProvider()
    if key == CachedTrendsProvider.name:
        return CachedTrendsProvider((cfg.get("cached") or {}).get("path", "data/trends.json"))
    raise SystemExit(f"Unknown trends provider '{key}'. Available: mock, cached")


def get_positivity_provider(name: Optional[str] = None, config: Optional[dict] = None) -> PositivityProvider:
    key = name or DEFAULT_POSITIVITY
    cfg = config or {}
    if key == MockPositivityProvider.name:
        return MockPositivityProvider()
    if key == GoogleSheetPositivityProvider.name:
        return GoogleSheetPositivityProvider(cfg.get("googlesheet", {}))
    if key == GSheetApiPositivityProvider.name:
        return GSheetApiPositivityProvider(cfg.get("gsheet_api", {}))
    raise SystemExit(f"Unknown positivity provider '{key}'. Available: mock, googlesheet, gsheet_api")


__all__ = [
    "TrendsProvider",
    "PositivityProvider",
    "get_trends_provider",
    "get_positivity_provider",
    "trends_available",
    "positivity_available",
    "DEFAULT_TRENDS",
    "DEFAULT_POSITIVITY",
]
