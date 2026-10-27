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
    # Per-shop overrides. Each listing shop finds its monitor category in the shop's own menu; set the
    # value here to pin it instead, which is what `main.py check-shops` tells you to do when a shop's
    # wording changes or the menu is rendered by script. Empty means "discover it".
    "shops_config": {"electroline": {"category_url": ""}, "scandia": {"catalog_path": ""},
                     "megaelectric": {"catalog_path": ""}, "stephanis": {"category_url": ""},
                     "public": {"findbar_token": ""}, "kotsovolos": {}},
    # what counts as a monitor worth watching; see monbot/criteria.py
    "criteria": {"sizes": [34], "panels": ["miniled", "ips"], "min_hz": 100,
                 "min_width": 3440, "min_height": 1440, "require_height_adjust": True,
                 "require_usb_c_pd_w": 65, "require_kvm": False, "require_vrr": False},
    # A shop-data-error filter, not a budget. The floor was 250 and a real 34-inch AOC at 249 fell
    # through it, which is the same mistake in the other direction as a cap set too low: the range has
    # to clear the junk a search returns (ink cartridges at 13 EUR, a phone at 50) without touching a
    # product anyone actually sells.
    "price_range": {"min": 150, "max": 1800},
    "scoring": {"fit_weight": 0.5, "review_weight": 0.5, "profile": "work"},
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
