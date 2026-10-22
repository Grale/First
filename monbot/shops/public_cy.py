"""public.cy - the storefront is an Angular SPA behind Akamai, but its search is served by findbar.io:

    POST https://app.findbar.io/api/v1/search?locale=el   (Bearer token = Public's own public front-end token)
    body {"query": "...", "filters": [], "initial": false, "page": 1, "size": 36, "sort": "_score", "dir": "desc"}
    -> results.hits[].source {displayName, finalPrice, listPrice, inStock, availability, url, brandName}

Exact model codes are not always tokenised by that index (a bare "34GP63A" may find nothing while the
title holds "LG34GP63AB"), so the adapter runs broad queries built from the criteria and lets the engine
match titles. Monitor model codes carry the size at the front, so "<brand> 34" is the query that reaches
them.
"""
from __future__ import annotations
import logging

import requests

from .base import MONITOR_BRANDS, Shop
from ..config import load as load_config
from ..criteria import active as active_criteria
from ..models import Item
from ..watchlist import Model

API = "https://app.findbar.io/api/v1/search?locale=el"
# Public's front-end token (scope: search, issued to the public.cy website; expires 2029). Override in
# config.json under "shops_config": {"public": {"findbar_token": "..."}} if Public rotates it.
DEFAULT_TOKEN = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                 "eyJkYXRhIjp7IndlYnNpdGVJZCI6MTUxLCJkb21haW4iOiJwdWJsaWMuY3kiLCJzY29wZXMiOlsic2VhcmNoIl0sIm5hbWUiOiJGcm9udGVuZCJ9LCJpYXQiOjE3OTA5NTAwMTEsImV4cCI6MTg4NTYyMjgxMSwiaXNzIjoiZmluZGJhci5pbyJ9."
                 "D-WYvYIlX9FK1iFlMK1LAyezYpaKDd9ciuIj-BIx_Ro")
# Broad queries, built from the criteria: every product word, every panel family term and every brand
# against every wanted size. A query that finds nothing costs one request, so covering more than one
# size stays cheap.
PAGE_SIZE = 36
MAX_PAGES = 3


class PublicCy(Shop):
    name = "public"
    label = "Public"
    base_url = "https://www.public.cy"
    start_tier = 1
    uses_search = True

    def _token(self) -> str:
        cfg = load_config()
        return (cfg.get("shops_config", {}).get("public", {}).get("findbar_token") or DEFAULT_TOKEN).strip()

    def _search(self, query: str) -> list[dict]:
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "Authorization": f"Bearer {self._token()}",
                   "Origin": self.base_url, "Referer": self.base_url + "/",
                   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}
        hits: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            body = {"query": query, "filters": [], "initial": False, "page": page, "size": PAGE_SIZE,
                    "sort": "_score", "dir": "desc"}
            self.f._throttle()
            r = requests.post(API, json=body, headers=headers, timeout=self.f.timeout)
            if r.status_code in (401, 403):
                raise RuntimeError(f"findbar token rejected ({r.status_code}); set shops_config.public.findbar_token")
            r.raise_for_status()
            res = r.json().get("results", {})
            page_hits = res.get("hits") or []
            hits.extend(page_hits)
            total = (res.get("total") or {}).get("value") or 0
            if len(page_hits) < PAGE_SIZE or page * PAGE_SIZE >= total:
                break
        return hits

    def _hit_to_item(self, h: dict) -> Item | None:
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
        queries = active_criteria().discovery_queries(MONITOR_BRANDS)
        seen: dict[str, Item] = {}
        failures = 0
        for q in queries:
            try:
                for h in self._search(q):
                    it = self._hit_to_item(h)
                    if it and it.shop_sku not in seen:
                        seen[it.shop_sku] = it
            except Exception as e:
                failures += 1
                self.log.warning("public search '%s' failed: %s", q, e)
                if failures >= 3:
                    raise
        self.log.info("public: %d distinct products from %d queries", len(seen), len(queries))
        return list(seen.values())

    def fetch_all_products(self) -> list[Item]:
        return self.fetch_items([])
