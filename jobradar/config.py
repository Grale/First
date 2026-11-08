"""Configuration loading. All tuning lives in profile/profile.yaml."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=4)
def load_profile(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else ROOT / "profile" / "profile.yaml"
    with open(p, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    total = sum(cfg["weights"].values())
    if round(total, 6) != 100:
        raise ValueError(f"profile.yaml weights must total 100, got {total}")
    return cfg


def load_text(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
