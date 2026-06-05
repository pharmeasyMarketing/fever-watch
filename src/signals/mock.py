"""Deterministic MOCK trends + positivity, seeded by (city, disease).

Mirrors the 'What's Going Around' prototype's buildSignals so the demo is stable
and realistic: trends are noisy with an occasional news spike; positivity is
smoother, amplitude-scaled by the disease's seasonal_push, and sparse in
semi-arid cities. Deterministic on purpose, so the committed grid.json does not
churn on every build. Swap for real providers when the feeds are ready.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from .base import PositivityProvider, TrendsProvider

SEED_VERSION = "v1"
SIGNAL_FLOOR = 4
_DIVISOR = float(16 ** 13)  # 13 hex chars = 52 bits of entropy


def _rng(seed: str, i: int) -> float:
    """Stable pseudo-random float in [0, 1) from a seed string and index."""
    digest = hashlib.sha256(f"{seed}|{i}".encode("utf-8")).hexdigest()
    return int(digest[:13], 16) / _DIVISOR


def _seed(city: dict, disease: dict) -> str:
    return f"{city['id']}|{disease['id']}|{SEED_VERSION}"


class MockTrendsProvider(TrendsProvider):
    name = "mock"

    def fetch(self, city: dict, disease: dict) -> dict:
        s = _seed(city, disease)
        push = disease.get("seasonal_push", 0.7)
        news_spike = _rng(s, 0) > 0.82
        value = round((0.3 + 0.7 * _rng(s, 1)) * 100 * push)
        if news_spike:
            value = min(100, value + 30)
        return {"value": max(SIGNAL_FLOOR, min(100, value)), "news_spike": news_spike}


class MockPositivityProvider(PositivityProvider):
    name = "mock"

    def fetch(self, city: dict, disease: dict) -> Optional[int]:
        s = _seed(city, disease)
        push = disease.get("seasonal_push", 0.7)
        value = round(min(100, (0.25 + 0.6 * _rng(s, 2)) * 100 * push))
        # Coverage is sparse: some semi-arid cities have no panel volume yet.
        sparse = city.get("climate") == "semi_arid" and _rng(s, 3) > 0.5
        if sparse:
            return None
        return max(SIGNAL_FLOOR, value)
