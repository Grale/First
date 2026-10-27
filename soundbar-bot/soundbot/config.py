from __future__ import annotations
import json
import threading
from copy import deepcopy
from typing import Any

from .paths import CONFIG_PATH

DEFAULTS: dict[str, Any] = {
    "ui": {"host": "127.0.0.1", "port": 8766},
    # interval_hours is how often a check runs at all. shop_interval_hours overrides it per shop, for
    # shops that should be asked less often than the rest: Skroutz is read a page at a time and
    # rate-limits a client that comes back every three hours, and a price watch does not need it to.
    "schedule": {"interval_hours": 3, "first_run_delay_minutes": 2,
                 "shop_interval_hours": {"skroutz": 12}},
    # When a shop turns the bot away, stop asking for a while instead of knocking every three hours.
    # The wait doubles for each block in a row and is cleared by the first successful read.
    "backoff": {"enabled": True, "first_hours": 6, "max_hours": 48},
    "rules": {"cross_shop_pct": 10, "list_discount_pct": 20, "back_in_stock": True, "dedupe_days": 7,
              # "country": only compare shops in the same country (a Greek price is not an offer in Cyprus);
              # "all": compare every shop against every other.
              "cross_shop_scope": "country"},
    "notify": {"toast": True, "ntfy": {"enabled": True, "server": "https://ntfy.sh", "topic": ""}},
    "shops": {"electroline": True, "scandia": True, "stephanis": True,
              "skroutz": True, "public_gr": True, "kotsovolos_gr": True},
    "countries": {"CY": True, "GR": True},
    "fetch": {"timeout_s": 40, "pause_s": 1.0, "playwright": "auto"},
    # what counts as a soundbar worth watching; see soundbot/criteria.py
    "criteria": {"min_height_channels": 2, "require_physical_height": True, "require_earc": True,
                 "no_wired_speakers": True, "require_sub_included": False,
                 "require_rears_included": False, "min_channels": 3.0},
    "price_range": {"min": 200, "max": 3500},
    "scoring": {"fit_weight": 0.5, "review_weight": 0.5, "profile": "cinema"},
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
