"""Tiny stdlib IO helpers shared by the builders.

write_json_atomic: write to a temp file in the same directory, then os.replace onto
the target. os.replace is atomic on a single filesystem, so a crash / kill / disk-full
mid-write can never leave a half-written or truncated JSON behind - the previous,
known-good file survives untouched. This is what makes the "fall back on last-good
data" behaviour safe: a failed pull never clobbers the committed-good weather/trends
file, so the daily grid keeps reading yesterday's real values instead of garbage.
"""
from __future__ import annotations

import json
import os
import tempfile


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_json_or(path: str, default=None):
    """Best-effort read: return `default` if the file is missing or unparseable
    (e.g. a previously truncated write) instead of raising."""
    try:
        return load_json(path)
    except (OSError, ValueError):
        return default


def write_json_atomic(path: str, payload, indent: int = 2) -> None:
    """Serialize `payload` to `path` atomically (temp file in the same dir + os.replace)."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=indent, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # atomic on the same filesystem
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
