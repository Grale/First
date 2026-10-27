"""public.gr - the storefront is an Angular app behind Akamai, but its search is served by findbar.io:

    POST https://app.findbar.io/api/v1/search?locale=el   (Bearer token = Public's own front-end token)
    body {"query": "...", "filters": [], "initial": false, "page": 1, "size": 36, "sort": "_score", "dir": "desc"}
    -> results.hits[].source {displayName, finalPrice, listPrice, inStock, availability, url, brandName}

The token is scoped to the website id, so the adapter reads it out of the shop's own front end and
caches it in .cache/. A token given in config.json wins over the discovered one:

    "shops_config": {"public_gr": {"findbar_token": "..."}}

Exact model codes are not tokenised by that index (searching "Q990H" finds nothing while the title holds
"HW-Q990H/EN"), so the adapter runs the broad queries the criteria build and lets the engine match titles.
"""
from __future__ import annotations
import base64
import json
import re
from typing import Optional

import requests

from .base import Shop
from ..config import load as load_config
from ..criteria import BRANDS, active as active_criteria
from ..models import Item
from ..paths import CACHE_DIR
from ..watchlist import Model

API = "https://app.findbar.io/api/v1/search?locale=el"
PAGE_SIZE = 36
MAX_PAGES = 3
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.(eyJ[A-Za-z0-9_-]{20,})\.[A-Za-z0-9_-]{10,}")
_SCRIPT_RE = re.compile(r'<script[^>]+src="([^"]+\.js[^"]*)"')


def _payload(jwt_body: str) -> dict:
    pad = "=" * (-len(jwt_body) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(jwt_body + pad))
    except Exception:
        return {}


class PublicLike(Shop):
    start_tier = 1
    uses_search = True
    domain = ""             # the domain the front-end token is issued to
    default_token = ""      # a token that was valid when this adapter was written

    # ---- token ------------------------------------------------------------
    @property
    def _cache_file(self):
        return CACHE_DIR / f"{self.name}-findbar-token.txt"

    def _configured_token(self) -> str:
        cfg = load_config()
        return (cfg.get("shops_config", {}).get(self.name, {}).get("findbar_token") or "").strip()

    def _discover_token(self) -> str:
        """Find the search token in the storefront's own front end."""
        html = self.f.get(self.base_url + "/", start_tier=self.start_tier)
        sources = [html]
        for src in _SCRIPT_RE.findall(html)[:12]:
            url = src if src.startswith("http") else self.base_url + "/" + src.lstrip("/")
            try:
                sources.append(self.f.get(url, start_tier=self.start_tier))
            except Exception as e:
                self.log.debug("%s: could not read %s: %s", self.name, url, e)
        for text in sources:
            for body in _JWT_RE.findall(text):
                data = (_payload(body) or {}).get("data") or {}
                if "search" in (data.get("scopes") or []) and data.get("domain") == self.domain:
                    token = next(m.group(0) for m in _JWT_RE.finditer(text) if m.group(1) == body)
                    self.log.info("%s: found findbar token for %s", self.name, self.domain)
                    return token
        raise RuntimeError(f"{self.name}: no findbar search token found on {self.base_url} "
                           f"(set shops_config.{self.name}.findbar_token)")

    def _token(self) -> str:
        token = self._configured_token()
        if token:
            return token
        if self._cache_file.exists():
            cached = self._cache_file.read_text(encoding="utf-8").strip()
            if cached:
                return cached
        if self.default_token:
            return self.default_token
        token = self._discover_token()
        CACHE_DIR.mkdir(exist_ok=True)
        self._cache_file.write_text(token, encoding="utf-8")
        return token

    def _forget_token(self) -> None:
        """Drop a rejected token so the next run discovers a fresh one."""
        try:
            self._cache_file.unlink(missing_ok=True)
        except OSError:
            pass

    # ---- search -----------------------------------------------------------
    def _search(self, query: str, token: str) -> list[dict]:
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "Authorization": f"Bearer {token}",
                   "Origin": self.base_url, "Referer": self.base_url + "/",
                   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
        hits: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            body = {"query": query, "filters": [], "initial": False, "page": page, "size": PAGE_SIZE,
                    "sort": "_score", "dir": "desc"}
            self.f._throttle()
            r = requests.post(API, json=body, headers=headers, timeout=self.f.timeout)
            if r.status_code in (401, 403):
                raise PermissionError(f"findbar token rejected ({r.status_code})")
            r.raise_for_status()
            res = r.json().get("results", {})
            page_hits = res.get("hits") or []
            hits.extend(page_hits)
            total = (res.get("total") or {}).get("value") or 0
            if len(page_hits) < PAGE_SIZE or page * PAGE_SIZE >= total:
                break
        return hits

    def _hit_to_item(self, h: dict) -> Optional[Item]:
        s = h.get("source") or {}
        title = (s.get("displayName") or "").strip()
        if not title:
            return None
        price = s.get("finalPrice")
        lp = s.get("listPrice")
        price = float(price) if price not in (None, "") else None
        lp = float(lp) if lp not in (None, "") else None
        list_price = lp if (lp and price and lp > price) else None
        url = s.get("url") or ""
        url = self.base_url + url if url.startswith("/") else (url or f"{self.base_url}/search?q={h.get('id', '')}")
        in_stock = s.get("inStock")
        avail = (s.get("availability") or "").lower()
        if in_stock is None and avail:
            in_stock = not any(k in avail for k in ("εξαντλ", "μη διαθέσιμ"))
        return Item(shop=self.name, title=title, price=price, url=url, list_price=list_price,
                    in_stock=bool(in_stock) if in_stock is not None else None, shop_sku=str(h.get("id") or ""))

    def fetch_items(self, models: list[Model]) -> list[Item]:
        queries = active_criteria().discovery_queries(BRANDS)
        token = self._token()
        seen: dict[str, Item] = {}
        failures = 0
        retried = False
        for q in queries:
            try:
                for h in self._search(q, token):
                    it = self._hit_to_item(h)
                    if it and it.shop_sku not in seen:
                        seen[it.shop_sku] = it
            except PermissionError as e:
                if retried:
                    raise RuntimeError(f"{self.name}: {e}; set shops_config.{self.name}.findbar_token") from e
                self.log.warning("%s: %s, looking for a fresh token", self.name, e)
                self._forget_token()
                token = self._discover_token()
                CACHE_DIR.mkdir(exist_ok=True)
                self._cache_file.write_text(token, encoding="utf-8")
                retried = True
            except Exception as e:
                failures += 1
                self.log.warning("%s search '%s' failed: %s", self.name, q, e)
                if failures >= 3:
                    raise
        self.log.info("%s: %d distinct products from %d queries", self.name, len(seen), len(queries))
        return list(seen.values())


class PublicGr(PublicLike):
    name = "public_gr"
    label = "Public"
    country = "GR"
    base_url = "https://www.public.gr"
    domain = "public.gr"
    default_token = ""      # discovered from the storefront on the first run
