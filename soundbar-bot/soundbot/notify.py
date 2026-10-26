"""Notifications: Windows toast (winotify) and ntfy.sh push."""
from __future__ import annotations
import logging
from typing import Optional

import requests

from .models import Alert

log = logging.getLogger("soundbot.notify")
APP_ID = "Soundbar Deal Bot"


def _toast(title: str, message: str, url: Optional[str]) -> bool:
    try:
        from winotify import Notification, audio
    except ImportError:
        log.warning("winotify not installed; toast skipped")
        return False
    try:
        n = Notification(app_id=APP_ID, title=title, msg=message[:250], duration="long")
        n.set_audio(audio.Default, loop=False)
        if url:
            n.add_actions(label="Open shop", launch=url)
        n.show()
        return True
    except Exception as e:  # pragma: no cover
        log.warning("toast failed: %s", e)
        return False


def _ntfy(cfg: dict, title: str, message: str, url: Optional[str], priority: int = 3,
          tags: Optional[list[str]] = None) -> bool:
    """Publish via ntfy's JSON endpoint (UTF-8 safe); priority is 1..5 (3 = default, 4 = high)."""
    n = cfg.get("notify", {}).get("ntfy", {})
    if not n.get("enabled") or not n.get("topic"):
        return False
    server = (n.get("server") or "https://ntfy.sh").rstrip("/")
    body = {"topic": n["topic"], "title": title, "message": message, "priority": int(priority),
            "tags": tags or ["loud_sound"]}
    if url:
        body["click"] = url
        body["actions"] = [{"action": "view", "label": "Open shop", "url": url}]
    try:
        r = requests.post(server, json=body, timeout=20)
        if r.status_code >= 300:
            log.warning("ntfy JSON publish returned %s: %s; retrying as plain text", r.status_code, r.text[:200])
            headers = {"Priority": str(int(priority))}
            if url:
                headers["Click"] = url
            r = requests.post(f"{server}/{n['topic']}", data=(title + "\n" + message).encode("utf-8"),
                              headers=headers, timeout=20)
            if r.status_code >= 300:
                log.warning("ntfy returned %s: %s", r.status_code, r.text[:200])
                return False
        return True
    except requests.RequestException as e:
        log.warning("ntfy failed: %s", e)
        return False


def send(cfg: dict, title: str, message: str, url: Optional[str] = None, priority: bool = False) -> list[str]:
    """Send on every enabled channel; returns the list of channels that succeeded."""
    sent: list[str] = []
    if cfg.get("notify", {}).get("toast", True):
        if _toast(title, message, url):
            sent.append("toast")
    if _ntfy(cfg, title, message, url, priority=4 if priority else 3,
             tags=["star", "loud_sound"] if priority else ["loud_sound"]):
        sent.append("ntfy")
    return sent


def send_alert(cfg: dict, a: Alert) -> list[str]:
    prefix = "⭐ " if a.priority else ""
    rule_title = {"cross_shop": "Cheaper shop", "list_discount": "Big discount", "back_in_stock": "Back in stock"}
    title = f"{prefix}{rule_title.get(a.rule, a.rule)}: {a.model_key}"
    return send(cfg, title, a.message, a.url, priority=a.priority)
