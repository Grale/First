from __future__ import annotations
import logging
import sys
from logging.handlers import RotatingFileHandler

from .paths import LOG_DIR


def setup(console: bool = True, level: int = logging.INFO) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    root = logging.getLogger()
    if getattr(root, "_soundbot_configured", False):
        return
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(LOG_DIR / "bot.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console and sys.stdout is not None:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        root.addHandler(ch)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    root._soundbot_configured = True  # type: ignore[attr-defined]
