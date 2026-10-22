from __future__ import annotations
import json
import threading
from copy import deepcopy
from typing import Any

from .paths import CONFIG_PATH

DEFAULTS: dict[str, Any] = {
    "ui": {"host": "127.0.0.1", "port": 8765},
    "schedule": {"interval_hours": 3, "first_run_delay_minutes": 2},
    "rules": {"cross_shop_pct": 10, "list_discount_pct": 20, "back_in_stock": True, "dedupe_days": 7},
    "notify": {"toast": True, "ntfy": {"enabled": True, "server": "https://ntfy.sh", "topic": ""}},
    "shops": {"electroline": True, "scandia": True, "megaelectric": True,
              "stephanis": True, "public": True, "kotsovolos": True},
    "fetch": {"timeout_s": 40, "pause_s": 1.0, "playwright": "auto"},
    # what counts as a TV worth watching; see tvbot/criteria.py
    "criteria": {"sizes": [75, 77], "panels": ["oled", "miniled"], "min_hz": 100,
                 "require_vrr": False, "require_hdmi21": False},
    "price_range": {"min": 700, "max": 9000},
    "scoring": {"fit_weight": 0.5, "review_weight": 0.5, "profile": "picture"},
}

_lock = threading.Lock()


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict[str, Any]:
    with _lock:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    return _merge(DEFAULTS, data)


def save(cfg: dict[str, Any]) -> None:
    with _lock:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
