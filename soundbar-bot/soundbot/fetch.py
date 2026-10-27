"""Tiered HTTP fetching.

tier 1  requests          plain HTTP with a browser User-Agent (Electroline, Scandia, Stephanis)
tier 2  curl_cffi         Chrome TLS/HTTP2 impersonation, passes Akamai-style bot checks (Public, Kotsovolos, Skroutz)
tier 3  playwright        real headless Chromium with a persistent profile (only if tier 2 is blocked and
                          playwright is installed)
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional

import requests

from .paths import PW_PROFILE

log = logging.getLogger("soundbot.fetch")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
}

BLOCK_MARKERS = ("Access Denied", "errors.edgesuite.net", "Request unsuccessful. Incapsula", "cf-browser-verification",
                 "Just a moment...", "Attention Required! | Cloudflare")


class FetchError(Exception):
    pass


class Blocked(FetchError):
    pass


def looks_blocked(status: int, text: str) -> bool:
    if status in (401, 403, 429, 503):
        return True
    head = text[:4000]
    return any(m in head for m in BLOCK_MARKERS)


class Fetcher:
    """One instance per run. Remembers which tier worked for each host."""

    def __init__(self, timeout: float = 40.0, pause: float = 1.0, playwright_mode: str = "auto"):
        self.timeout = timeout
        self.pause = pause
        self.playwright_mode = playwright_mode  # auto | never | always
        self._session = requests.Session()
        self._session.headers.update(BASE_HEADERS)
        self._cffi = None
        self._pw = None
        self._pw_ctx = None
        self._lock = threading.Lock()
        self.tier_used: dict[str, str] = {}
        self._last_request_at = 0.0

    # ---- helpers ----------------------------------------------------------
    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self.pause - (now - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def close(self) -> None:
        try:
            if self._pw_ctx is not None:
                self._pw_ctx.close()
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # pragma: no cover
            pass
        self._pw_ctx = None
        self._pw = None

    # ---- tiers ------------------------------------------------------------
    def get_requests(self, url: str, **kw) -> str:
        self._throttle()
        r = self._session.get(url, timeout=self.timeout, **kw)
        if looks_blocked(r.status_code, r.text):
            raise Blocked(f"requests tier blocked ({r.status_code}) for {url}")
        r.raise_for_status()
        return r.text

    def get_cffi(self, url: str, headers: Optional[dict] = None) -> str:
        self._throttle()
        if self._cffi is None:
            from curl_cffi import requests as cr  # imported lazily
            self._cffi = cr.Session(impersonate="chrome")
        h = {"Accept-Language": BASE_HEADERS["Accept-Language"]}
        if headers:
            h.update(headers)
        r = self._cffi.get(url, timeout=self.timeout, headers=h)
        if looks_blocked(r.status_code, r.text):
            raise Blocked(f"curl_cffi tier blocked ({r.status_code}) for {url}")
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code} for {url}")
        return r.text

    def get_playwright(self, url: str, wait_selector: Optional[str] = None, wait_ms: int = 2500) -> str:
        if self.playwright_mode == "never":
            raise Blocked("playwright disabled in config")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise Blocked("playwright not installed (pip install playwright && python -m playwright install chromium)") from e
        with self._lock:
            if self._pw is None:
                self._pw = sync_playwright().start()
                PW_PROFILE.mkdir(exist_ok=True)
                self._pw_ctx = self._pw.chromium.launch_persistent_context(
                    str(PW_PROFILE), headless=True, user_agent=UA, locale="el-GR",
                    viewport={"width": 1366, "height": 900})
            page = self._pw_ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=15000)
                    except Exception:
                        pass
                page.wait_for_timeout(wait_ms)
                html = page.content()
            finally:
                page.close()
        if looks_blocked(200, html):
            raise Blocked(f"playwright tier blocked for {url}")
        return html

    # ---- public -----------------------------------------------------------
    def get(self, url: str, start_tier: int = 1, wait_selector: Optional[str] = None) -> str:
        """Fetch with escalation. start_tier=2 skips plain requests (for Akamai-protected shops)."""
        host = url.split("/")[2]
        tiers = [t for t in (1, 2, 3) if t >= start_tier]
        last: Optional[Exception] = None
        for t in tiers:
            try:
                if t == 1:
                    html = self.get_requests(url)
                elif t == 2:
                    html = self.get_cffi(url)
                else:
                    html = self.get_playwright(url, wait_selector=wait_selector)
                self.tier_used[host] = {1: "requests", 2: "curl_cffi", 3: "playwright"}[t]
                return html
            except Blocked as e:
                log.info("tier %s blocked for %s: %s", t, host, e)
                last = e
            except requests.RequestException as e:
                log.warning("tier %s network error for %s: %s", t, host, e)
                last = e
                if t == 1:
                    continue
                break
            except Exception as e:  # curl_cffi / playwright errors
                log.warning("tier %s error for %s: %s", t, host, e)
                last = e
        # Keep the kind of the last failure: a block is a different problem from a timeout, and
        # the engine backs off a shop that blocks rather than retrying it on the next check.
        kind = Blocked if isinstance(last, Blocked) else FetchError
        raise kind(f"all tiers failed for {url}: {last}")

    def get_json(self, url: str, start_tier: int = 2):
        import json
        text = self.get_cffi(url, headers={"Accept": "application/json"}) if start_tier >= 2 else self.get_requests(url)
        return json.loads(text)
