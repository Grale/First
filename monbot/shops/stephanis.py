"""stephanis.com.cy - server-rendered category pages, 100 cards per page.

Card: div.property-spotlight-slide-2 > a[href=/en/products/.../<id>] ; li.tile-product-name (title) ;
      .product-code ; .large-now-price.with-sale (price) ; .large-stephanis-card-price (loyalty-card price)

The monitor category path is read from the shop's menu or pinned in config.json under
`shops_config.stephanis.category_url`; the paging query string is appended here.
"""
from __future__ import annotations
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import Shop, find_category_links, parse_price, shop_config
from ..models import Item
from ..watchlist import Model

HOME_URL = "https://www.stephanis.com.cy/en/"
PAGING = "view=thumbnails&recordsPerPage=100&sortBy=name&page={page}"
MAX_PAGES = 10
_PRODUCTS_HREF = re.compile(r"/en/products/", re.I)


class Stephanis(Shop):
    name = "stephanis"
    label = "Stephanis"
    base_url = "https://www.stephanis.com.cy"
    start_tier = 1

    def _with_paging(self, url: str) -> str:
        if "{page}" in url:
            return url
        parts = urlsplit(url)
        query = PAGING if not parts.query else f"{parts.query}&{PAGING}"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

    def category_templates(self) -> list[str]:
        """Every PC-monitor category to read, as URLs with `{page}` and the paging query appended.

        Stephanis keeps a second PC-monitor aisle under last-pieces, which is clearance stock and so
        worth more to a deal bot than the main listing. Both are read and merged.
        """
        pinned = shop_config(self.name).get("category_url") or ""
        if isinstance(pinned, str):
            pinned = [pinned] if pinned.strip() else []
        urls = [u.strip() for u in pinned if u.strip()]
        if not urls:
            html = self.f.get(HOME_URL, start_tier=self.start_tier)
            urls = find_category_links(html, self.base_url, _PRODUCTS_HREF)
            if not urls:
                raise RuntimeError(
                    "Stephanis: no monitor category found in the site menu. Open stephanis.com.cy, go to the "
                    "monitors category, and put its URL in config.json under "
                    '"shops_config": {"stephanis": {"category_url": "..."}}')
            self.log.info("stephanis: reading %d discovered categories: %s", len(urls), ", ".join(urls))
        return [self._with_paging(u) for u in urls]

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
        empty: list[str] = []
        for template in self.category_templates():
            for page in range(1, MAX_PAGES + 1):
                url = template.format(page=page)
                html = self.f.get(url, start_tier=self.start_tier)
                page_items = self._parse(html)
                if page == 1 and not page_items:
                    empty.append(url)
                fresh = [i for i in page_items if i.url not in seen]
                for i in fresh:
                    seen.add(i.url)
                items.extend(fresh)
                if len(page_items) < 100 or not fresh:
                    break
        if not items:
            raise RuntimeError(
                f"Stephanis: no product cards on {', '.join(empty) or 'any discovered category'}. Either the "
                'layout changed or these are not monitor categories; pin one in config.json under '
                '"shops_config".stephanis.category_url')
        self.log.info("stephanis: %d distinct products across categories", len(items))
        return items
