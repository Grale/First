from __future__ import annotations
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from ..config import load as load_config
from ..fetch import Fetcher
from ..models import Item
from ..watchlist import Model

log = logging.getLogger("monbot.shops")

_PRICE_RE = re.compile(r"(\d[\d\s.,]*\d|\d)")

# Words a shop uses for its monitor aisle, in both languages. Used to find the category from the shop's
# own navigation rather than hardcoding a URL that only the shop can change.
MONITOR_WORDS = ("MONITOR", "MONITORS", "ΟΘΟΝΕΣ", "ΟΘΟΝΗ", "ΟΘΟΝΩΝ")

# Brands to query at the shops that answer searches instead of listing a category. Monitor brands, which
# overlap the TV brands only at LG, Samsung and Philips.
MONITOR_BRANDS = ("Dell", "LG", "Samsung", "AOC", "MSI", "Gigabyte", "Asus", "Acer", "BenQ", "Philips",
                  "HP", "Lenovo", "Iiyama", "ViewSonic", "Corsair", "Alienware")
_HREF_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TAGS_RE = re.compile(r"<[^>]+>")


def shop_config(name: str) -> dict:
    """Per-shop settings from config.json "shops_config", e.g. a category URL override."""
    return (load_config().get("shops_config") or {}).get(name) or {}


def find_category_links(html: str, base_url: str, must_match: re.Pattern) -> list[str]:
    """Absolute URLs of links whose text names a monitor aisle and whose href matches `must_match`.

    The six shops each moved their monitor category at some point, and a hardcoded URL is the one thing
    in an adapter that breaks silently - the page still returns 200, it just holds other products. So
    the category is read from the shop's own menu, and config can pin it when a shop's wording changes.
    """
    out: list[str] = []
    for href, inner in _HREF_RE.findall(html):
        text = _TAGS_RE.sub(" ", inner).replace("&nbsp;", " ").upper()
        words = set(re.findall(r"[A-ZΑ-ΩΆΈΉΊΌΎΏ]+", text))
        if not words & set(MONITOR_WORDS):
            continue
        if not must_match.search(href):
            continue
        url = urljoin(base_url, href)
        if url not in out:
            out.append(url)
    return out


def parse_price(text: Optional[str]) -> Optional[float]:
    """'€1, 199.00' -> 1199.0 ; '697 ,99€' -> 697.99 ; '1.199,00 €' -> 1199.0"""
    if not text:
        return None
    m = _PRICE_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    s = re.sub(r"\s+", "", m.group(1))
    # decide decimal separator: the last of '.' or ',' followed by exactly 2 digits
    if re.search(r"[.,]\d{2}$", s):
        dec = s[-3]
        s = s[:-3].replace(".", "").replace(",", "") + "." + s[-2:]
        _ = dec
    else:
        s = s.replace(".", "").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


class Shop:
    """Base class. Subclasses implement fetch_items(); the engine matches items to the watchlist."""
    name = "base"
    label = "Base"
    base_url = ""
    start_tier = 1
    uses_search = False     # True when the shop is queried per watchlist model

    def __init__(self, fetcher: Fetcher):
        self.f = fetcher
        self.log = logging.getLogger(f"monbot.shops.{self.name}")

    # Either return the whole monitor listing (listing shops) or search per model (search shops).
    def fetch_items(self, models: list[Model]) -> list[Item]:
        raise NotImplementedError

    # Used by the discovery scan. Listing shops just reuse fetch_items.
    def fetch_all_products(self) -> list[Item]:
        return self.fetch_items([])

    @staticmethod
    def search_terms(model: Model) -> list[str]:
        """Shortest distinctive query per model: the model key, then the first alias without spaces."""
        terms = [model.model_key]
        for a in model.aliases:
            if a and a.upper() != model.model_key.upper():
                terms.append(a)
        return terms[:2]
