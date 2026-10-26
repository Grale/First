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

# ...and the aisles that also say "monitor" and sell something else entirely. Every shop checked has at
# least two: Electroline files blood-pressure monitors, baby monitors and temperature-humidity monitors
# under that word, Scandia sells DJ monitors (speakers), and Stephanis has monitor cables and monitor
# brackets. Without this list the category finder picks whichever matched first, which is luck.
NON_MONITOR_WORDS = ("BLOOD", "PRESSURE", "ΠΙΕΣΗΣ", "ΠΙΕΣΟΜΕΤΡΑ", "BABY", "ΜΩΡΟΥ", "DJ", "STUDIO",
                     "TEMPERATURE", "HUMIDITY", "HEART", "FITNESS", "BRACKET", "BRACKETS", "MOUNT",
                     "MOUNTS", "ARM", "ARMS", "STAND", "STANDS", "CABLE", "CABLES", "ΚΑΛΩΔΙΑ",
                     "ΒΡΑΧΙΟΝΕΣ", "ΒΑΣΕΙΣ")

# Brands to query at the shops that answer searches instead of listing a category. Monitor brands, which
# overlap the TV brands only at LG, Samsung and Philips.
MONITOR_BRANDS = ("Dell", "LG", "Samsung", "AOC", "MSI", "Gigabyte", "Asus", "Acer", "BenQ", "Philips",
                  "HP", "Lenovo", "Iiyama", "ViewSonic", "Corsair", "Alienware")
_HREF_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TAGS_RE = re.compile(r"<[^>]+>")


def shop_config(name: str) -> dict:
    """Per-shop settings from config.json "shops_config", e.g. a category URL override."""
    return (load_config().get("shops_config") or {}).get(name) or {}


def _words(text: str) -> set[str]:
    """Upper-case word tokens, so short markers match whole words only ("DJ", never "ADJUSTABLE")."""
    from ..criteria import fold_greek
    return set(re.findall(r"[A-Z0-9ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ]+", fold_greek(text)))


def find_category_links(html: str, base_url: str, must_match: re.Pattern) -> list[str]:
    """Absolute URLs of links that name a PC-monitor aisle and whose href matches `must_match`.

    The six shops each moved their monitor category at some point, and a hardcoded URL is the one thing
    in an adapter that breaks silently - the page still returns 200, it just holds other products. So
    the category is read from the shop's own menu, and config can pin it when a shop's wording changes.

    Both the link text and the href are tested, because a shop's menu label is often just "Monitors"
    while the slug says what kind ("blood-pressure-monitors", "pc-monitor-brackets").
    """
    out: list[str] = []
    for href, inner in _HREF_RE.findall(html):
        text = _TAGS_RE.sub(" ", inner).replace("&nbsp;", " ")
        words = _words(text) | _words(href)
        if not words & set(MONITOR_WORDS):
            continue
        if words & set(NON_MONITOR_WORDS):
            continue
        if not must_match.search(href):
            continue
        url = urljoin(base_url, href)
        if url not in out:
            out.append(url)
    return out


def parse_price(text: Optional[str]) -> Optional[float]:
    """'€1, 199.00' -> 1199.0 ; '697 ,99€' -> 697.99 ; '1.199,00 €' -> 1199.0 ; '1099.0' -> 1099.0

    The last '.' or ',' is the decimal separator when one or two digits follow it to the end, and a
    thousands separator otherwise ('1.099' is 1099, '1.09' is 1.09).

    One decimal digit has to count. Kotsovolos's API returns its selling price as "1099.0", and
    treating only two-digit decimals as decimals turned that into 10990 - every price from that shop
    came out ten times too high, which pushed them all past the price cap so the shop silently matched
    nothing at all. A parser that is wrong by a factor of ten is worse than one that fails outright.
    """
    if not text:
        return None
    m = _PRICE_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    s = re.sub(r"\s+", "", m.group(1))
    dec = re.search(r"[.,](\d{1,2})$", s)
    if dec:
        s = s[:dec.start()].replace(".", "").replace(",", "") + "." + dec.group(1)
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
