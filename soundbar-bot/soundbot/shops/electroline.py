"""electroline.cy - each category page embeds `var pageProducts = {...}` with every product on it.

Two categories hold soundbars: the soundbar list itself and the "speaker bases and soundbars" list that
holds a few of the all-in-one models.
"""
from __future__ import annotations
import json

from .base import Shop, parse_price
from ..models import Item
from ..watchlist import Model

CATEGORY_URLS = (
    "https://electroline.cy/en/product-category/sound-vision/sound/soundbars/",
    "https://electroline.cy/en/product-category/sound-vision/sound/speaker-bases-and-soundbars/",
)
MARK = "var pageProducts = "


class Electroline(Shop):
    name = "electroline"
    label = "Electroline"
    country = "CY"
    base_url = "https://electroline.cy"
    start_tier = 1

    def _parse(self, html: str, url: str) -> list[Item]:
        i = html.find(MARK)
        if i < 0:
            raise RuntimeError(f"pageProducts blob not found on {url} (layout changed?)")
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
        return items

    def fetch_items(self, models: list[Model]) -> list[Item]:
        items: list[Item] = []
        seen: set[str] = set()
        for url in CATEGORY_URLS:
            html = self.f.get(url, start_tier=self.start_tier)
            for it in self._parse(html, url):
                if it.shop_sku not in seen:
                    seen.add(it.shop_sku)
                    items.append(it)
        self.log.info("electroline: %d products on %d category pages", len(items), len(CATEGORY_URLS))
        return items
