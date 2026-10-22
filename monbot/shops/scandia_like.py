"""scandia.cy and megaelectric.cy share one platform: server-rendered catalog pages, 20 cards each.

Catalog URLs carry a numeric category id (`/catalog/Televisions-195-1.html`), so the monitor category
cannot be guessed from its name alone. The id is read from the shop's own menu, or pinned in
config.json under `shops_config.<shop>.catalog_path` as a template containing `{page}`.
"""
from __future__ import annotations
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Shop, find_category_links, parse_price, shop_config
from ..models import Item
from ..watchlist import Model

MAX_PAGES = 12
_CATALOG_HREF = re.compile(r"/catalog/[^/\"]+-\d+-\d+\.html$", re.I)
_PAGE_TAIL = re.compile(r"-(\d+)\.html$")


class ScandiaLike(Shop):
    start_tier = 1

    def catalog_path(self) -> str:
        """Path template for the monitor catalog, with `{page}` where the page number goes."""
        pinned = (shop_config(self.name).get("catalog_path") or "").strip()
        if pinned:
            return pinned if "{page}" in pinned else _PAGE_TAIL.sub("-{page}.html", pinned)
        html = self.f.get(self.base_url + "/", start_tier=self.start_tier)
        links = find_category_links(html, self.base_url, _CATALOG_HREF)
        if not links:
            raise RuntimeError(
                f"{self.label}: no monitor catalog link found in the site menu. Open {self.base_url}, go to "
                f'the monitors catalog, and put its path in config.json under "shops_config": '
                f'{{"{self.name}": {{"catalog_path": "/catalog/Monitors-<id>-{{page}}.html"}}}}')
        path = links[0][len(self.base_url):] if links[0].startswith(self.base_url) else links[0]
        template = _PAGE_TAIL.sub("-{page}.html", path)
        self.log.info("%s: using discovered catalog %s", self.name, template)
        return template

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
        path = self.catalog_path()
        items: list[Item] = []
        seen_urls: set[str] = set()
        first_page_urls: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            url = self.base_url + path.format(page=page)
            html = self.f.get(url, start_tier=self.start_tier)
            page_items = self._parse_cards(html)
            urls = {i.url for i in page_items}
            if page == 1:
                first_page_urls = urls
                if not page_items:
                    raise RuntimeError(
                        f"{self.label}: no product cards on {url}. Either the layout changed or this is not "
                        f'the monitor catalog; pin it in config.json under "shops_config".{self.name}.catalog_path')
            elif not page_items or urls == first_page_urls or urls <= seen_urls:
                break  # catalog wraps around to page 1 after the last page
            for it in page_items:
                if it.url not in seen_urls:
                    seen_urls.add(it.url)
                    items.append(it)
            if len(page_items) < 20:
                break
        self.log.info("%s: %d products on %d catalog pages", self.name, len(items), page)
        return items


class Scandia(ScandiaLike):
    name = "scandia"
    label = "Scandia"
    base_url = "https://scandia.cy"


class MegaElectric(ScandiaLike):
    name = "megaelectric"
    label = "MegaElectric"
    base_url = "https://megaelectric.cy"
