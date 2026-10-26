from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
WATCHLIST_PATH = ROOT / "watchlist.json"
DB_PATH = ROOT / "prices.db"
LOG_DIR = ROOT / "logs"
PW_PROFILE = ROOT / ".pw-profile"
SCHEDULER_DIR = ROOT / "scheduler"
CACHE_DIR = ROOT / ".cache"
