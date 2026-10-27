"""scandia.cy - server-rendered catalog pages, 20 cards each.

Category 202 is Sound Bars.
"""
from __future__ import annotations
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Shop, parse_price
from ..models import Item
from ..watchlist import Model

MAX_PAGES = 8


class ScandiaLike(Shop):
    country = "CY"
    start_tier = 1
    catalog_path = "/catalog/Sound-Bars-202-{page}.html"

    def _parse_cards(self, html: str) -> list[Item]:
        soup = BeautifulSoup(html, "lxml")
        items: list[Item] = []
        for card in soup.select("div.product-card"):
            a = None
            for cand in card.select("a[href*='/products/']"):
                if cand.get_text(" ", strip=True):
                    a = cand
                    break
            if a is None:
                a = card.select_one("a[href*='/products/']")
            if a is None:
                continue
            url = urljoin(self.base_url, a.get("href", ""))
            title = a.get_text(" ", strip=True)
            if not title:
                img = card.select_one("img[alt]")
                title = (img.get("alt") or "").strip() if img else ""
            title = title.replace("&quot;", '"')
            price_el = card.select_one("span.catalog-price")
            strike_el = card.select_one("span.strike-price")
            price = parse_price(price_el.get_text(" ", strip=True)) if price_el else None
            strike = parse_price(strike_el.get_text(" ", strip=True)) if strike_el else None
            list_price = strike if (strike and price and strike > price) else None
            text = card.get_text(" ", strip=True).lower()
            in_stock = not any(k in text for k in ("out of stock", "sold out", "εξαντλ"))
            sku = ""
            m = re.search(r"-(\d+)-\d+\.html$", url)
            if m:
                sku = m.group(1)
            if title:
                items.append(Item(shop=self.name, title=title, price=price, url=url, list_price=list_price,
                                  in_stock=in_stock, shop_sku=sku))
        return items

    def fetch_items(self, models: list[Model]) -> list[Item]:
        items: list[Item] = []
        seen_urls: set[str] = set()
        first_page_urls: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            url = self.base_url + self.catalog_path.format(page=page)
            html = self.f.get(url, start_tier=self.start_tier)
            page_items = self._parse_cards(html)
            urls = {i.url for i in page_items}
            if page == 1:
                first_page_urls = urls
            elif not page_items or urls == first_page_urls or urls <= seen_urls:
                break  # catalog wraps around to page 1 after the last page
            for it in page_items:
                if it.url not in seen_urls:
                    seen_urls.add(it.url)
                    items.append(it)
            if len(page_items) < 20:
                break
        self.log.info("%s: %d soundbars on %d catalog pages", self.name, len(items), page)
        return items


class Scandia(ScandiaLike):
    name = "scandia"
    label = "Scandia"
    base_url = "https://scandia.cy"

