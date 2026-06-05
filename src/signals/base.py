"""Swappable interfaces for the two non-weather signals (trends, positivity).

Real providers (a managed Google Trends API, the PharmEasy lab feed) drop in
behind these ABCs without touching the grid builder, exactly as the weather
providers do for signal 1. v1 ships deterministic MOCK providers (see mock.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class TrendsProvider(ABC):
    """Signal 2: population search attention (coincident)."""

    name: str = "base"

    @abstractmethod
    def fetch(self, city: dict, disease: dict) -> dict:
        """Return {"value": int 0-100, "news_spike": bool} for one city/disease."""
        raise NotImplementedError


class PositivityProvider(ABC):
    """Signal 3: PharmEasy lab positivity (lagging ground truth).

    Returns None where no ground-truth data exists for a city/disease (coverage
    is sparse by design). Always surfaced as an aggregate city-level TREND, never
    a re-identifiable rate.
    """

    name: str = "base"

    @abstractmethod
    def fetch(self, city: dict, disease: dict) -> Optional[int]:
        """Return int 0-100 positivity, or None when there is no data."""
        raise NotImplementedError
