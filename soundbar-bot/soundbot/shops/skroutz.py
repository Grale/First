"""skroutz.gr - the Greek price comparison site.

Skroutz lists one price per product: it picks a shop, fulfils the order itself and quotes delivery on
top, which is why a single "best price" per model is the number worth watching.

What this adapter reads, and what it will not read
--------------------------------------------------
Skroutz's robots.txt allows the pages this adapter uses and forbids several neighbouring ones, so the
paths are checked in code rather than trusted to stay right by habit:

    allowed     /search?keyphrase=<model>      one query per watched model
                /c/<id>/<slug>.html            the soundbar category, for the discovery scan
                /s/<id>/<slug>.html            a product page, only when a price needs confirming
    forbidden   /api/, /apiv2/, /products/show, /products/compare_selected_products,
                /s/*/shops_list, /s/*/price_graph, /s/*/recommendations, any URL with filter_id=

`_assert_allowed` refuses a URL that falls in the second group, so this adapter cannot drift into the
Skroutz API or into the per-shop price lists behind a product page.

Skroutz does not publish the page markup as an interface, so the parser is anchored on the product
links themselves (`/s/<id>/<slug>`) and reads the title and the price out of the card around each link,
rather than on class names that can be renamed overnight. If Skroutz ever changes enough that nothing
parses, the adapter raises instead of reporting an empty shop, so a run fails loudly and the previous
snapshot is kept.
"""
from __future__ import annotations
import re
from typing import Iterable, Optional
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup

from .base import Shop, parse_price
from ..models import Item
from ..watchlist import Model

CATEGORY_PATH = "/c/907/soundbars.html"      # override in shops_config.skroutz.category_path
SEARCH_PATH = "/search?keyphrase={q}"
SKU_HREF = re.compile(r"^/s/(\d+)/")
PRICE_TEXT = re.compile(r"\d[\d.,]*\s*€")
# robots.txt, User-agent: * - the prefixes this adapter must never request
FORBIDDEN_PREFIXES = ("/api/", "/apiv2/", "/products/show", "/products/compare_selected_products",
                      "/suggest", "/autocomplete/", "/personalization/", "/comparelists/", "/cart",
                      "/checkout/", "/users/", "/account/", "/sign_in", "/signup", "/cdn-cgi/")
FORBIDDEN_SUFFIXES = ("/shops_list", "/price_graph", "/recommendations")
MAX_CARDS_PER_QUERY = 24


class Skroutz(Shop):
    name = "skroutz"
    label = "Skroutz"
    country = "GR"
    base_url = "https://www.skroutz.gr"
    start_tier = 2          # Skroutz turns away the plain requests tier
    uses_search = True

    # ---- robots ------------------------------------------------------------
    @staticmethod
    def _assert_allowed(url: str) -> str:
        parts = urlsplit(url)
        path = parts.path
        if any(path.startswith(p) for p in FORBIDDEN_PREFIXES):
            raise ValueError(f"skroutz: {path} is disallowed by robots.txt for every crawler")
        if any(path.endswith(s) for s in FORBIDDEN_SUFFIXES):
            raise ValueError(f"skroutz: {path} is disallowed by robots.txt for every crawler")
        if "filter_id=" in (parts.query or ""):
            raise ValueError("skroutz: filtered category URLs are disallowed by robots.txt")
        return url

    def _get(self, path: str) -> str:
        url = self._assert_allowed(urljoin(self.base_url, path))
        return self.f.get(url, start_tier=self.start_tier)

    # ---- parsing -----------------------------------------------------------
    def _cards(self, html: str) -> list[Item]:
        """One item per product link, with the title and price taken from the card around it."""
        soup = BeautifulSoup(html, "lxml")
        items: dict[str, Item] = {}
        for a in soup.select('a[href^="/s/"]'):
            href = a.get("href") or ""
            m = SKU_HREF.match(href)
            if not m:
                continue
            sku = m.group(1)
            if sku in items:
                continue
            title = (a.get_text(" ", strip=True) or a.get("title") or "").strip()
            if not title:
                img = a.select_one("img[alt]")
                title = (img.get("alt") or "").strip() if img else ""
            card = a
            price: Optional[float] = None
            for _ in range(5):          # walk out of the link until the card's price comes into view
                if card is None:
                    break
                found = PRICE_TEXT.search(card.get_text(" ", strip=True))
                if found:
                    price = parse_price(found.group(0))
                    if not title:
                        title = card.get_text(" ", strip=True)[:160]
                    break
                card = card.parent
            if not title:
                continue
            items[sku] = Item(shop=self.name, title=title, price=price,
                              url=urljoin(self.base_url, href.split("?")[0]),
                              list_price=None, in_stock=None, shop_sku=sku)
            if len(items) >= MAX_CARDS_PER_QUERY:
                break
        return list(items.values())

    def _parse_or_raise(self, html: str, what: str) -> list[Item]:
        items = self._cards(html)
        if not items and 'href="/s/' not in html:
            raise RuntimeError(f"skroutz: no product links on {what} (layout changed, or the page was "
                               f"served as a bot check)")
        return items

    # ---- Shop interface ----------------------------------------------------
    def _queries(self, models: Iterable[Model]) -> list[str]:
        """One query per model: the model key, which is what a Skroutz title carries."""
        out: list[str] = []
        for m in models:
            for term in self.search_terms(m):
                if term and term not in out:
                    out.append(term)
                    break
        return out

    def fetch_items(self, models: list[Model]) -> list[Item]:
        if not models:
            return self.fetch_all_bars()
        found: dict[str, Item] = {}
        failures = 0
        queries = self._queries(models)
        for q in queries:
            try:
                html = self._get(SEARCH_PATH.format(q=quote(q)))
                for it in self._parse_or_raise(html, f"search for {q}"):
                    found.setdefault(it.shop_sku, it)
            except Exception as e:
                failures += 1
                self.log.warning("skroutz search '%s' failed: %s", q, e)
                if failures >= 3:
                    raise
        self.log.info("skroutz: %d distinct products from %d model searches", len(found), len(queries))
        return list(found.values())

    def fetch_all_bars(self) -> list[Item]:
        from ..config import load as load_config
        path = (load_config().get("shops_config", {}).get(self.name, {}).get("category_path")
                or CATEGORY_PATH)
        items: dict[str, Item] = {}
        for page in range(1, 4):
            sep = "&" if "?" in path else "?"
            html = self._get(path if page == 1 else f"{path}{sep}page={page}")
            page_items = self._parse_or_raise(html, f"category page {page}")
            new = [i for i in page_items if i.shop_sku not in items]
            for it in new:
                items[it.shop_sku] = it
            if not new:
                break
        self.log.info("skroutz: %d products in the soundbar category", len(items))
        return list(items.values())
