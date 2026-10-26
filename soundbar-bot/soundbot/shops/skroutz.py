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
from typing import Optional
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup

from .base import Shop, parse_price
from ..models import Item
from ..watchlist import Model

# The soundbar category, confirmed on skroutz.gr. Override per shop in shops_config.<name>.category_path.
CATEGORY_PATH = "/c/1735/soundbar.html"
# 358 products in the Greek category at the time of writing, around two dozen to a page. The loop stops
# early as soon as a page adds nothing new, so this is a ceiling rather than a cost.
CATEGORY_PAGES = 18
SEARCH_PATH = "/search?keyphrase={q}"
SKU_HREF = re.compile(r"^/s/(\d+)/")
PRICE_TEXT = re.compile(r"\d[\d.,]*\s*€")
# robots.txt, User-agent: * - the prefixes this adapter must never request
FORBIDDEN_PREFIXES = ("/api/", "/apiv2/", "/products/show", "/products/compare_selected_products",
                      "/suggest", "/autocomplete/", "/personalization/", "/comparelists/", "/cart",
                      "/checkout/", "/users/", "/account/", "/sign_in", "/signup", "/cdn-cgi/")
FORBIDDEN_SUFFIXES = ("/shops_list", "/price_graph", "/recommendations")
# A search page leads with sponsored and related strips before the results proper, and a category page
# lists dozens of products, so the cap has to be well clear of both or the real rows get cut off.
MAX_CARDS_PER_PAGE = 150


class SkroutzLike(Shop):
    start_tier = 2          # Skroutz turns away the plain requests tier
    uses_search = True

    # ---- robots ------------------------------------------------------------
    @staticmethod
    def _assert_allowed(url: str) -> str:
        parts = urlsplit(url)
        path = parts.path
        if any(path.startswith(p) for p in FORBIDDEN_PREFIXES):
            raise ValueError(f"{path} is disallowed by robots.txt for every crawler")
        if any(path.endswith(s) for s in FORBIDDEN_SUFFIXES):
            raise ValueError(f"{path} is disallowed by robots.txt for every crawler")
        if "filter_id=" in (parts.query or ""):
            raise ValueError("filtered category URLs are disallowed by robots.txt")
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
            if len(items) >= MAX_CARDS_PER_PAGE:
                break
        return list(items.values())

    def _parse_or_raise(self, html: str, what: str) -> list[Item]:
        """Parse a page that must hold products. Only for the first page of a listing.

        An empty page is a normal answer everywhere else - the page after the last one of a category,
        or a search that found nothing - so raising there would turn the end of a listing into a failed
        shop. It is only evidence of a wrong path or a bot check when it is the first page asked for.
        """
        items = self._cards(html)
        if not items and 'href="/s/' not in html:
            raise RuntimeError(f"{self.name}: no product links on {what} (wrong path, changed layout, "
                               f"or the page was served as a bot check)")
        return items

    # ---- Shop interface ----------------------------------------------------
    @staticmethod
    def _query_for(m: Model) -> str:
        """Brand and model together: 'Samsung HW-Q990F', not 'HW-Q990F'.

        A bare part number is not reliably tokenised by the search index, and a query that finds
        nothing still returns a page full of sponsored and related products, which is how a search per
        model could come back with hundreds of items and almost no matches.
        """
        return f"{m.brand} {m.model_key}".strip()

    def fetch_items(self, models: list[Model]) -> list[Item]:
        """The category listing first, then one search for whatever it did not cover.

        The soundbar category lists every model with its price in a handful of requests, so it is both
        cheaper and more complete than a search per model; the searches are the fallback for a model
        filed under another category, or one the category pages did not reach.
        """
        if not models:
            return self.fetch_all_bars()
        from ..criteria import active as active_criteria
        from ..match import best_match

        found: dict[str, Item] = {}
        try:
            for it in self.fetch_all_bars():
                found.setdefault(it.shop_sku, it)
        except Exception as e:
            self.log.warning(
                "%s: the category listing at %s did not read (%s). Falling back to one search per "
                'model. If this keeps happening, open Skroutz, click through to Soundbars, and put that '
                'URL\'s path in config.json under "shops_config": {"skroutz": {"category_path": '
                '"/c/<id>/<slug>.html"}}', self.name, self._category_path(), e)
        from_category = len(found)

        crit = active_criteria()
        covered = {m.model_key for it in found.values()
                   for m in [best_match(it.title, models, crit)] if m is not None}
        missing = [m for m in models if m.model_key not in covered]

        failures = 0
        for m in missing:
            q = self._query_for(m)
            try:
                hits = self._cards(self._get(SEARCH_PATH.format(q=quote(q))))
                if not hits:
                    self.log.debug("%s: no results for '%s'", self.name, q)
                for it in hits:
                    found.setdefault(it.shop_sku, it)
            except Exception as e:
                failures += 1
                self.log.warning("%s search '%s' failed: %s", self.name, q, e)
                if failures >= 3:
                    raise
        self.log.info("%s: %d products (%d from the category listing, %d searches for the models it "
                      "did not cover)", self.name, len(found), from_category, len(missing))
        return list(found.values())

    def _category_path(self) -> str:
        from ..config import load as load_config
        return (load_config().get("shops_config", {}).get(self.name, {}).get("category_path")
                or CATEGORY_PATH)

    def fetch_all_bars(self) -> list[Item]:
        path = self._category_path()
        items: dict[str, Item] = {}
        for page in range(1, CATEGORY_PAGES + 1):
            sep = "&" if "?" in path else "?"
            html = self._get(path if page == 1 else f"{path}{sep}page={page}")
            page_items = (self._parse_or_raise(html, "the category listing") if page == 1
                          else self._cards(html))
            new = [i for i in page_items if i.shop_sku not in items]
            for it in new:
                items[it.shop_sku] = it
            if not new:
                break
        self.log.info("%s: %d products over %d category page(s)", self.name, len(items), page)
        return list(items.values())


class Skroutz(SkroutzLike):
    name = "skroutz"
    label = "Skroutz GR"
    country = "GR"
    base_url = "https://www.skroutz.gr"


class SkroutzCy(SkroutzLike):
    """skroutz.cy - the same catalogue and the same category ids as skroutz.gr, filtered to what can
    actually be delivered to Cyprus.

    Worth checking alongside the Greek site rather than instead of it: the prices are the two markets'
    own, and a model that shows on skroutz.gr but not here is one that will not ship to Cyprus, which
    is as useful to know as a price.
    """
    name = "skroutz_cy"
    label = "Skroutz CY"
    country = "CY"
    base_url = "https://www.skroutz.cy"
