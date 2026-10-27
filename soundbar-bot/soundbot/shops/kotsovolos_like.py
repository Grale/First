"""kotsovolos.gr - Next.js front end over HCL Commerce, behind Akamai (needs the Chrome-TLS tier).

search   GET /SearchDisplay?q=<term>&storeId=<id>   -> __NEXT_DATA__.props.pageProps.pageData.productIds
details  GET /api/ext/getProductDetailsByPartNumbers?partNumbers=[..]&storeId=<id> -> catalogEntryView[]
stock    GET /api/inventory/product/availability/<singleSKUCatalogEntryID>?...&storeId=<id>

The adapter reads the store id out of the shop's own __NEXT_DATA__ and caches it in .cache/; a value in
config.json wins:

    "shops_config": {"kotsovolos_gr": {"store_id": "10151"}}

Product pages need the exact SEO slug, so offers link to the search page for the part number.
"""
from __future__ import annotations
import json
import re
from collections import Counter
from urllib.parse import quote

from .base import Shop, parse_price
from ..config import load as load_config
from ..criteria import BRANDS, active as active_criteria
from ..match import best_match
from ..models import Item
from ..paths import CACHE_DIR
from ..watchlist import Model

NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
# The store id turns up in several shapes depending on where it is written: as a JSON field in
# __NEXT_DATA__, as the same field escaped inside a JSON string, and as a query parameter on the links
# the page builds. Backslashes are optional everywhere so one pattern covers escaped and plain alike.
_STORE_PATTERNS = (
    re.compile(r'\\?"store(?:Id|ID)\\?"\s*:\s*\\?"?(\d{4,6})'),
    re.compile(r'[?&]storeId=(\d{4,6})'),
    re.compile(r'\\?"(?:currentStoreId|defaultStoreId|catalogStoreId|myStoreId)\\?"\s*:\s*\\?"?(\d{4,6})'),
)
# Pages to look on, in order. The search page builds more store-scoped links than the home page does.
_DISCOVERY_PATHS = ("/", "/SearchDisplay?q=soundbar")
UNAVAILABLE_KEYS = ("OUT_OF_STOCK", "SOLD_OUT", "NOT_AVAILABLE", "UNAVAILABLE", "DISCONTINUED")
DETAIL_CHUNK = 15


class KotsovolosLike(Shop):
    start_tier = 2
    uses_search = True
    default_store = ""

    # ---- store id ---------------------------------------------------------
    @property
    def _cache_file(self):
        return CACHE_DIR / f"{self.name}-store-id.txt"

    def _discover_store(self) -> str:
        """Read the store id out of the shop's own pages, with enough of a report to act on if it is
        not there: which pages were read, how big they were, and whether __NEXT_DATA__ was present."""
        counts: Counter[str] = Counter()
        seen: list[str] = []
        for path in _DISCOVERY_PATHS:
            try:
                html = self.f.get(self.base_url + path, start_tier=self.start_tier)
            except Exception as e:
                seen.append(f"{path}: {type(e).__name__}: {str(e)[:80]}")
                continue
            m = NEXT_DATA.search(html)
            hay = m.group(1) if m else html
            for pattern in _STORE_PATTERNS:
                counts.update(pattern.findall(hay))
            seen.append(f"{path}: {len(html)} bytes, __NEXT_DATA__ {'yes' if m else 'no'}, "
                        f"{sum(counts.values())} id(s) so far")
            if counts:
                break
        if not counts:
            raise RuntimeError(
                f"{self.name}: no storeId on {self.base_url} [{'; '.join(seen)}]. Open the shop in a "
                f"browser, view source, search for storeId, and put it in config.json under "
                f'"shops_config": {{"{self.name}": {{"store_id": "…"}}}}')
        store = counts.most_common(1)[0][0]      # the id the page uses most is the storefront's own
        self.log.info("%s: discovered storeId %s (candidates %s)", self.name, store, dict(counts))
        return store

    def store_id(self) -> str:
        cfg = load_config()
        configured = str(cfg.get("shops_config", {}).get(self.name, {}).get("store_id") or "").strip()
        if configured:
            return configured
        if self._cache_file.exists():
            cached = self._cache_file.read_text(encoding="utf-8").strip()
            if cached:
                return cached
        if self.default_store:
            return self.default_store
        store = self._discover_store()
        CACHE_DIR.mkdir(exist_ok=True)
        self._cache_file.write_text(store, encoding="utf-8")
        return store

    # ---- API helpers ------------------------------------------------------
    def _search_ids(self, query: str, store: str) -> list[int]:
        url = f"{self.base_url}/SearchDisplay?q={quote(query)}&storeId={store}"
        html = self.f.get(url, start_tier=self.start_tier)
        m = NEXT_DATA.search(html)
        if not m:
            raise RuntimeError(f"{self.name}: __NEXT_DATA__ missing on search page")
        data = json.loads(m.group(1))
        page = data.get("props", {}).get("pageProps", {}).get("pageData", {}) or {}
        return [int(x) for x in page.get("productIds") or []]

    def _details(self, part_numbers: list[int], store: str) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(part_numbers), DETAIL_CHUNK):
            ids = ",".join(str(p) for p in part_numbers[i:i + DETAIL_CHUNK])
            url = (f"{self.base_url}/api/ext/getProductDetailsByPartNumbers?partNumbers=[{ids}]"
                   f"&storeId={store}")
            data = self.f.get_json(url, start_tier=2)
            out.extend(data.get("catalogEntryView") or [])
        return out

    def _in_stock(self, sku_id: str, store: str):
        if not sku_id:
            return None
        url = (f"{self.base_url}/api/inventory/product/availability/{sku_id}?fc_Id=ALL&homeDelivery=true"
               f"&pickupStoreDelivery=true&expressHomeDelivery=true&expressHomeDeliveryBigBox=true"
               f"&checkLastPieces=true&qty=1&storeId={store}")
        try:
            data = self.f.get_json(url, start_tier=2)
        except Exception as e:  # availability is best effort
            self.log.info("%s availability failed for %s: %s", self.name, sku_id, e)
            return None
        key = str(data.get("availableStatusKey") or "").upper()
        if not key:
            return None
        return not any(k in key for k in UNAVAILABLE_KEYS)

    def _entry_to_item(self, e: dict, store: str) -> Item:
        """The selling price is the "Offer" entry (it matches the shop page); "price_EUR" holds stale
        values. "Display" is shown struck through only when it is above the offer."""
        title = (e.get("name") or "").strip()
        prices = {p.get("usage"): parse_price(str(p.get("value") or "")) for p in e.get("price") or []}
        price = prices.get("Offer") or parse_price(str(e.get("price_EUR") or ""))
        display = prices.get("Display")
        list_price = display if (display and price and display > price) else None
        part = str(e.get("partNumber") or "")
        url = f"{self.base_url}/SearchDisplay?q={part}&storeId={store}"
        return Item(shop=self.name, title=title, price=price, url=url, list_price=list_price,
                    in_stock=None, shop_sku=part)

    def _collect(self, queries: list[str], store: str) -> list[dict]:
        ids: list[int] = []
        seen: set[int] = set()
        failures = 0
        for q in queries:
            try:
                for pid in self._search_ids(q, store):
                    if pid not in seen:
                        seen.add(pid)
                        ids.append(pid)
            except Exception as e:
                failures += 1
                self.log.warning("%s search '%s' failed: %s", self.name, q, e)
                if failures >= 3:
                    raise
        return self._details(ids, store)

    # ---- Shop interface ---------------------------------------------------
    def fetch_items(self, models: list[Model]) -> list[Item]:
        crit = active_criteria()
        store = self.store_id()
        queries = [self.search_terms(m)[0] for m in models] or crit.discovery_queries(BRANDS)
        entries = self._collect(queries, store)
        items: list[Item] = []
        seen: set[str] = set()
        for e in entries:
            it = self._entry_to_item(e, store)
            if not it.title or it.shop_sku in seen:
                continue
            seen.add(it.shop_sku)
            if best_match(it.title, models, crit) is not None:
                it.in_stock = self._in_stock(str(e.get("singleSKUCatalogEntryID") or ""), store)
            items.append(it)
        self.log.info("%s: %d distinct products from %d searches", self.name, len(items), len(queries))
        return items

    def fetch_all_bars(self) -> list[Item]:
        store = self.store_id()
        entries = self._collect(active_criteria().discovery_queries(BRANDS), store)
        items: list[Item] = []
        seen: set[str] = set()
        for e in entries:
            it = self._entry_to_item(e, store)
            if it.title and it.shop_sku not in seen:
                seen.add(it.shop_sku)
                items.append(it)
        return items


class KotsovolosGr(KotsovolosLike):
    name = "kotsovolos_gr"
    label = "Kotsovolos"
    country = "GR"
    base_url = "https://www.kotsovolos.gr"
    default_store = ""      # discovered from the storefront on the first run
