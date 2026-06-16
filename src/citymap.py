"""Reusable lab-city -> config-city resolver (signal 3).

One source of truth for mapping a raw PharmEasy/ThyroCare lab city string to a
Fever Watch config city id, used by BOTH the historic (2025) transform and the
live (2026) feed so "this year" overlays "last year" on the same city axis.

Resolution is EXACT (case-insensitive, whitespace-collapsed) only - it never
strips state suffixes or guesses, because that is exactly what re-introduces the
cross-state collisions the cleanup removed (e.g. AURANGABAD(BH) must NOT match
config aurangabad). Vetted variants live in data/citymap/city_alias_map.csv;
manual folds (e.g. satellite towns -> parent metro) in manual_aliases.csv. Any
unseen string returns None (treated as "no data" downstream) and is recorded so
it can be reviewed and added to the manual map - correctness over coverage.

Stdlib only.
"""
from __future__ import annotations

import csv
import json
import os
from typing import Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALIAS = os.path.join(_ROOT, "data", "citymap", "city_alias_map.csv")
_MANUAL = os.path.join(_ROOT, "data", "citymap", "manual_aliases.csv")
_CONFIG = os.path.join(_ROOT, "config", "cities.json")


def _key(s: str) -> str:
    return " ".join(str(s).strip().upper().split())


class CityResolver:
    def __init__(self, alias_path: str = _ALIAS, manual_path: str = _MANUAL, config_path: str = _CONFIG):
        self._map: dict[str, str] = {}
        self._ids: set[str] = set()
        self.unmapped: dict[str, int] = {}  # raw_key -> hit count

        with open(config_path, encoding="utf-8") as f:
            cities = json.load(f)["cities"]
        for c in cities:
            cid = c["id"]
            self._ids.add(cid)
            for token in [cid, c.get("name", ""), *c.get("aliases", [])]:
                if token:
                    self._map.setdefault(_key(token), cid)

        # vetted observed-data map + manual folds (manual overrides config defaults)
        for path in (alias_path, manual_path):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        raw = row.get("raw")
                        cid = (row.get("config_id") or "").strip()
                        if raw and cid:
                            self._map[_key(raw)] = cid

        # guard: every target id must be a real config city
        bad = {cid for cid in self._map.values() if cid not in self._ids}
        if bad:
            raise ValueError(f"alias map points to non-config ids: {sorted(bad)}")

    def resolve(self, raw: Optional[str]) -> Optional[str]:
        if not raw or not str(raw).strip():
            return None
        cid = self._map.get(_key(raw))
        if cid is None:
            k = _key(raw)
            self.unmapped[k] = self.unmapped.get(k, 0) + 1
        return cid

    def dump_unmapped(self, path: str) -> int:
        rows = sorted(self.unmapped.items(), key=lambda kv: -kv[1])
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["raw_string", "hits"])
            w.writerows(rows)
        return len(rows)


if __name__ == "__main__":  # quick self-test
    r = CityResolver()
    tests = {
        "MUMBAI": "mumbai", "mumbai": "mumbai", "Bengaluru": "bengaluru", "bangalore": "bengaluru",
        "COCHIN": "kochi", "GOA": "panaji", "NORTH GOA": "panaji", "BILASPUR": "bilaspur",
        "KALYAN": "thane", "DOMBIVLI": "thane", "MIRA ROAD": "mumbai", "VIRAR": "mumbai", "NALASOPARA": "mumbai",
        "AURANGABAD": "aurangabad", "AURANGABAD(BH)": None, "NADIA": None, "KALYANI": None, "ZZZ NOWHERE": None,
    }
    ok = 0
    for raw, exp in tests.items():
        got = r.resolve(raw)
        flag = "OK" if got == exp else "FAIL"
        if got == exp:
            ok += 1
        print(f"  [{flag}] {raw!r:18} -> {got!r} (expected {exp!r})")
    print(f"{ok}/{len(tests)} passed | map size {len(r._map)} | config ids {len(r._ids)}")
