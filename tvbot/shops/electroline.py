"""electroline.cy - the TV category page embeds `var pageProducts = {...}` with every TV."""
from __future__ import annotations
import json

from .base import Shop, parse_price
from ..models import Item
from ..watchlist import Model

CATEGORY_URL = "https://electroline.cy/en/product-category/sound-vision/tvs/tv-s/"
MARK = "var pageProducts = "


class Electroline(Shop):
    name = "electroline"
    label = "Electroline"
    base_url = "https://electroline.cy"
    start_tier = 1

    def fetch_items(self, models: list[Model]) -> list[Item]:
        html = self.f.get(CATEGORY_URL, start_tier=self.start_tier)
        i = html.find(MARK)
        if i < 0:
            raise RuntimeError("pageProducts blob not found on Electroline TV page (layout changed?)")
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
                              url=p.get("permalink") or CATEGORY_URL, list_price=list_price,
                              in_stock=in_stock, shop_sku=str(sku)))
        self.log.info("electroline: %d TVs on listing", len(items))
        return items
