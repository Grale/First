"""stephanis.com.cy - server-rendered soundbar category, 100 cards per page.

Card: div.property-spotlight-slide-2 > a[href=/en/products/.../<id>] ; li.tile-product-name (title) ;
      .product-code ; .large-now-price.with-sale (price) ; .large-was-price (struck-through price)

Titles carry the channel layout and the model year ("HW-Q990H/EN (2026) ... 11.1.4"), which is what the
discovery scan reads to spot a soundbar that is not on the watchlist yet.
"""
from __future__ import annotations
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Shop, parse_price
from ..models import Item
from ..watchlist import Model

CATEGORY = ("https://www.stephanis.com.cy/en/products/sound-and-vision/home-cinema-and-sound/sound-bars"
            "?view=thumbnails&recordsPerPage=100&sortBy=name&page={page}")
MAX_PAGES = 5


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
            text = card.get_text(" ", strip=True).lower()
            in_stock = None if "availability" in text else True
            if any(k in text for k in ("out of stock", "sold out", "εξαντλ")):
                in_stock = False
            items.append(Item(shop=self.name, title=title, price=price, url=url, list_price=list_price,
                              in_stock=in_stock, shop_sku=sku))
        return items

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
        self.log.info("stephanis: %d soundbars on %d pages", len(items), page)
        return items
