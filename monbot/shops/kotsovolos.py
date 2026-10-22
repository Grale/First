"""kotsovolos.cy - Next.js front end over HCL Commerce, behind Akamai (needs the Chrome-TLS tier).

search   GET /SearchDisplay?q=<term>&storeId=10161   -> __NEXT_DATA__.props.pageProps.pageData.productIds (part numbers)
details  GET /api/ext/getProductDetailsByPartNumbers?partNumbers=[..]&storeId=10161 -> catalogEntryView[] (name, price)
stock    GET /api/inventory/product/availability/<singleSKUCatalogEntryID>?...&storeId=10161 -> availableStatusKey

Product pages need the exact SEO slug, so offers link to the search page for the part number.
"""
from __future__ import annotations
import json
import re
from urllib.parse import quote

from .base import MONITOR_BRANDS, Shop, parse_price
from ..criteria import active as active_criteria
from ..match import best_match
from ..models import Item
from ..watchlist import Model

STORE = "10161"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
UNAVAILABLE_KEYS = ("OUT_OF_STOCK", "SOLD_OUT", "NOT_AVAILABLE", "UNAVAILABLE", "DISCONTINUED")
# Brands for the discovery scan come from shops.base; the product, panel and size terms come from the
# criteria.
DETAIL_CHUNK = 15


class Kotsovolos(Shop):
    name = "kotsovolos"
    label = "Kotsovolos"
    base_url = "https://www.kotsovolos.cy"
    start_tier = 2
    uses_search = True

    # ---- API helpers ------------------------------------------------------
    def _search_ids(self, query: str) -> list[int]:
        url = f"{self.base_url}/SearchDisplay?q={quote(query)}&storeId={STORE}"
        html = self.f.get(url, start_tier=self.start_tier)
        m = NEXT_DATA.search(html)
        if not m:
            raise RuntimeError("Kotsovolos: __NEXT_DATA__ missing on search page")
        data = json.loads(m.group(1))
        page = data.get("props", {}).get("pageProps", {}).get("pageData", {}) or {}
        return [int(x) for x in page.get("productIds") or []]

    def _details(self, part_numbers: list[int]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(part_numbers), DETAIL_CHUNK):
            chunk = part_numbers[i:i + DETAIL_CHUNK]
            ids = ",".join(str(p) for p in chunk)
            url = f"{self.base_url}/api/ext/getProductDetailsByPartNumbers?partNumbers=[{ids}]&storeId={STORE}"
            data = self.f.get_json(url, start_tier=2)
            out.extend(data.get("catalogEntryView") or [])
        return out

    def _in_stock(self, sku_id: str):
        if not sku_id:
            return None
        url = (f"{self.base_url}/api/inventory/product/availability/{sku_id}?fc_Id=ALL&homeDelivery=true"
               f"&pickupStoreDelivery=true&expressHomeDelivery=true&expressHomeDeliveryBigBox=true"
               f"&checkLastPieces=true&qty=1&storeId={STORE}")
        try:
            data = self.f.get_json(url, start_tier=2)
        except Exception as e:  # availability is best effort
            self.log.info("kotsovolos availability failed for %s: %s", sku_id, e)
            return None
        key = str(data.get("availableStatusKey") or "").upper()
        if not key:
            return None
        return not any(k in key for k in UNAVAILABLE_KEYS)

    def _entry_to_item(self, e: dict) -> Item:
        """The selling price is the "Offer" entry (it matches the shop page); "price_EUR" holds stale values.
        "Display" is shown struck through only when it is above the offer."""
        title = (e.get("name") or "").strip()
        prices = {p.get("usage"): parse_price(str(p.get("value") or "")) for p in e.get("price") or []}
        price = prices.get("Offer") or parse_price(str(e.get("price_EUR") or ""))
        display = prices.get("Display")
        list_price = display if (display and price and display > price) else None
        part = str(e.get("partNumber") or "")
        url = f"{self.base_url}/SearchDisplay?q={part}&storeId={STORE}"
        return Item(shop=self.name, title=title, price=price, url=url, list_price=list_price,
                    in_stock=None, shop_sku=part)

    def _collect(self, queries: list[str]) -> list[dict]:
        ids: list[int] = []
        seen: set[int] = set()
        failures = 0
        for q in queries:
            try:
                for pid in self._search_ids(q):
                    if pid not in seen:
                        seen.add(pid)
                        ids.append(pid)
            except Exception as e:
                failures += 1
                self.log.warning("kotsovolos search '%s' failed: %s", q, e)
                if failures >= 3:
                    raise
        return self._details(ids)

    # ---- Shop interface ---------------------------------------------------
    def fetch_items(self, models: list[Model]) -> list[Item]:
        crit = active_criteria()
        queries = [self.search_terms(m)[0] for m in models]
        entries = self._collect(queries)
        items: list[Item] = []
        seen: set[str] = set()
        for e in entries:
            it = self._entry_to_item(e)
            if not it.title or it.shop_sku in seen:
                continue
            seen.add(it.shop_sku)
            if best_match(it.title, models, crit) is not None:
                it.in_stock = self._in_stock(str(e.get("singleSKUCatalogEntryID") or ""))
            items.append(it)
        self.log.info("kotsovolos: %d distinct products from %d model searches", len(items), len(queries))
        return items

    def fetch_all_products(self) -> list[Item]:
        entries = self._collect(active_criteria().discovery_queries(MONITOR_BRANDS))
        items: list[Item] = []
        seen: set[str] = set()
        for e in entries:
            it = self._entry_to_item(e)
            if it.title and it.shop_sku not in seen:
                seen.add(it.shop_sku)
                items.append(it)
        return items
