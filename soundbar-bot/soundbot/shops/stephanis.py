"""stephanis.com.cy - server-rendered soundbar category, 100 cards per page.

Card: div.property-spotlight-slide-2 > a[href=/en/products/.../<id>] ; li.tile-product-name (title) ;
      .product-code ; .large-now-price.with-sale (price) ; .large-was-price (struck-through price)

Titles carry the channel layout and the model year ("HW-Q990H/EN (2026) ... 11.1.4"), which is what the
discovery scan reads to spot a soundbar that is not on the watchlist yet.

Stock is not on the category page. The card's add-to-cart block is filled in by JavaScript and its
"Availability" link is a link rather than an answer, so nothing there says whether a product can
actually be bought. The product page does, in the JSON blob it embeds for its own front end:

    ISAVAILABLEONLINE           1 when the product can be ordered online at all
    ISINVENTORYTRACKINGENABLED  true when QUANTITYAVAILABLE is meaningful
    QUANTITYAVAILABLE           units on hand; 0 is the sold-out case
    ONLINEAVAILABILITYMESSAGE   the shop's own wording when it is not orderable

So the adapter reads the listing, and then fetches the product page for the models actually being
watched - a handful of requests - rather than guessing from the category page.
"""
from __future__ import annotations
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Shop, parse_price
from ..criteria import active as active_criteria
from ..match import best_match
from ..models import Item
from ..watchlist import Model

CATEGORY = ("https://www.stephanis.com.cy/en/products/sound-and-vision/home-cinema-and-sound/sound-bars"
            "?view=thumbnails&recordsPerPage=100&sortBy=name&page={page}")
MAX_PAGES = 5
# Stock is only looked up for watched models, but a watchlist that grows should not turn into a crawl.
MAX_STOCK_LOOKUPS = 25


def _field(html: str, key: str) -> str:
    """The raw value of "KEY": ... in the product page's data blob, '' when it is not there."""
    m = re.search(r'"%s"\s*:\s*("(?:[^"\\]|\\.)*"|[^,}\s]+)' % re.escape(key), html)
    return m.group(1).strip().strip('"') if m else ""


class Stephanis(Shop):
    name = "stephanis"
    label = "Stephanis"
    country = "CY"
    base_url = "https://www.stephanis.com.cy"
    start_tier = 1

    def _parse(self, html: str) -> list[Item]:
        soup = BeautifulSoup(html, "lxml")
        items: list[Item] = []
        for card in soup.select("div.property-spotlight-slide-2, div[class*='js-layout-product-container']"):
            name_el = card.select_one("li.tile-product-name")
            if name_el is None:
                continue
            title = name_el.get_text(" ", strip=True)
            link = card.select_one("a[href*='/products/']")
            url = urljoin(self.base_url, link.get("href", "")) if link else self.base_url
            price_el = card.select_one(".large-now-price.with-sale") or card.select_one(".large-now-price")
            price = parse_price(price_el.get_text(" ", strip=True)) if price_el else None
            was_el = card.select_one(".large-was-price")
            was = parse_price(was_el.get_text(" ", strip=True)) if was_el else None
            list_price = was if (was and price and was > price) else None
            code_el = card.select_one(".product-code")
            sku = code_el.get_text(strip=True) if code_el else (name_el.get("data-productid") or "")
            # Stock comes from the product page; the card cannot answer it.
            items.append(Item(shop=self.name, title=title, price=price, url=url, list_price=list_price,
                              in_stock=None, shop_sku=sku))
        return items

    def _in_stock(self, url: str):
        """Whether the product can be bought now, or None when the page does not say."""
        try:
            html = self.f.get(url, start_tier=self.start_tier)
        except Exception as e:
            self.log.info("stephanis: no stock for %s: %s", url, e)
            return None
        online = _field(html, "ISAVAILABLEONLINE")
        if online in ("0", "false"):
            return False
        qty, tracking = _field(html, "QUANTITYAVAILABLE"), _field(html, "ISINVENTORYTRACKINGENABLED")
        if tracking == "true" and qty:
            try:
                return float(qty) > 0
            except ValueError:
                return None
        # Orderable with no inventory tracking: the shop sells it to order, which is not out of stock.
        return True if online == "1" else None

    def fetch_items(self, models: list[Model]) -> list[Item]:
        items: list[Item] = []
        seen: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            html = self.f.get(CATEGORY.format(page=page), start_tier=self.start_tier)
            page_items = self._parse(html)
            new = [i for i in page_items if i.url not in seen]
            for i in new:
                seen.add(i.url)
            items.extend(new)
            if len(page_items) < 100 or not new:
                break
        crit = active_criteria()
        looked_up = 0
        for it in items:
            if looked_up >= MAX_STOCK_LOOKUPS:
                break
            if best_match(it.title, models, crit) is None:
                continue
            it.in_stock = self._in_stock(it.url)
            looked_up += 1
        self.log.info("stephanis: %d soundbars on %d pages, stock checked for %d",
                      len(items), page, looked_up)
        return items
