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

    def category_urls(self) -> list[str]:
        """Every PC-monitor category to read, most general first.

        Electroline splits monitors into office and gaming subcategories and keeps a separate
        clearance aisle. The parent category holds both subcategories but not the clearance one, and
        the clearance aisle is exactly where a deal bot should be looking, so all of them are read and
        merged by SKU rather than one being chosen.
        """
        pinned = shop_config(self.name).get("category_url") or ""
        if isinstance(pinned, str):
            pinned = [pinned] if pinned.strip() else []
        if pinned:
            return [u.strip() for u in pinned if u.strip()]
        html = self.f.get(HOME_URL, start_tier=self.start_tier)
        links = find_category_links(html, self.base_url, _CATEGORY_HREF)
        if not links:
            raise RuntimeError(
                "Electroline: no monitor category found in the site menu. Open electroline.cy, go to the "
                "monitors category, and put its URL in config.json under "
                '"shops_config": {"electroline": {"category_url": "..."}}')
        # most general first: a shallower path is the parent of the others
        links.sort(key=lambda u: u.rstrip("/").count("/"))
        self.log.info("electroline: reading %d discovered categories: %s", len(links), ", ".join(links))
        return links

    def _parse_blob(self, html: str, url: str) -> list[Item]:
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
        return items

    def fetch_items(self, models: list[Model]) -> list[Item]:
        seen: dict[str, Item] = {}
        errors: list[str] = []
        for url in self.category_urls():
            try:
                for it in self._parse_blob(self.f.get(url, start_tier=self.start_tier), url):
                    seen.setdefault(it.shop_sku, it)
            except Exception as e:
                errors.append(f"{url}: {e}")
                self.log.warning("electroline category failed %s: %s", url, e)
        if not seen:
            raise RuntimeError("Electroline: no products read from any monitor category. " +
                               ("; ".join(errors) if errors else "The categories were empty."))
        self.log.info("electroline: %d distinct products across categories", len(seen))
        return list(seen.values())
