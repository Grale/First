"""electroline.cy - a category page embeds `var pageProducts = {...}` with every product in it.

The TV build read the TV category. The monitor category URL is not hardcoded here because it is the
kind of constant that breaks silently: pin it in config.json under
`shops_config.electroline.category_url`, or let the adapter read it from the shop's own menu.
"""
from __future__ import annotations
import json
import re

from .base import Shop, find_category_links, parse_price, shop_config
from ..models import Item
from ..watchlist import Model

HOME_URL = "https://electroline.cy/en/"
MARK = "var pageProducts = "
_CATEGORY_HREF = re.compile(r"/product-category/", re.I)


class Electroline(Shop):
    name = "electroline"
    label = "Electroline"
    base_url = "https://electroline.cy"
    start_tier = 1

    def category_url(self) -> str:
        pinned = (shop_config(self.name).get("category_url") or "").strip()
        if pinned:
            return pinned
        html = self.f.get(HOME_URL, start_tier=self.start_tier)
        links = find_category_links(html, self.base_url, _CATEGORY_HREF)
        if not links:
            raise RuntimeError(
                "Electroline: no monitor category found in the site menu. Open electroline.cy, go to the "
                "monitors category, and put its URL in config.json under "
                '"shops_config": {"electroline": {"category_url": "..."}}')
        # the deepest path is the most specific category ("/computing/monitors/" over "/computing/")
        links.sort(key=lambda u: -u.count("/"))
        self.log.info("electroline: using discovered category %s", links[0])
        return links[0]

    def fetch_items(self, models: list[Model]) -> list[Item]:
        url = self.category_url()
        html = self.f.get(url, start_tier=self.start_tier)
        i = html.find(MARK)
        if i < 0:
            raise RuntimeError(f"pageProducts blob not found on {url} (layout changed, or not a category page?)")
        blob, _ = json.JSONDecoder().raw_decode(html, i + len(MARK))
        items: list[Item] = []
        for sku, p in blob.items():
            title = (p.get("title") or "").replace("&quot;", '"').strip()
            if not title:
                continue
            price = p.get("price")
            if isinstance(price, str):
                price = parse_price(price)
            regular = parse_price(str(p.get("regular_price") or ""))
            list_price = regular if (regular and price and regular > price) else None
            meta = p.get("meta") or {}
            in_stock = bool(p.get("isAvailableOnline") or p.get("isAvailableInStores") or meta.get("instock"))
            items.append(Item(shop=self.name, title=title, price=float(price) if price else None,
                              url=p.get("permalink") or url, list_price=list_price,
                              in_stock=in_stock, shop_sku=str(sku)))
        self.log.info("electroline: %d products on listing", len(items))
        return items
