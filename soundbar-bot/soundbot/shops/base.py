from __future__ import annotations
import logging
import re
from typing import Optional

from ..fetch import Fetcher
from ..models import Item
from ..watchlist import Model

log = logging.getLogger("soundbot.shops")

_PRICE_RE = re.compile(r"(\d[\d\s.,]*\d|\d)")


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
        s = s[:-3].replace(".", "").replace(",", "") + "." + s[-2:]
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
    country = "CY"          # CY or GR; the cross-shop rule compares within one country by default
    base_url = ""
    start_tier = 1
    uses_search = False     # True when the shop is queried per watchlist model

    def __init__(self, fetcher: Fetcher):
        self.f = fetcher
        self.log = logging.getLogger(f"soundbot.shops.{self.name}")

    # Either return the whole soundbar listing (listing shops) or search per model (search shops).
    def fetch_items(self, models: list[Model]) -> list[Item]:
        raise NotImplementedError

    # Used by the discovery scan. Listing shops just reuse fetch_items.
    def fetch_all_bars(self) -> list[Item]:
        return self.fetch_items([])

    @staticmethod
    def search_terms(model: Model) -> list[str]:
        """Shortest distinctive query per model: the model key, then the first alias without spaces."""
        terms = [model.model_key]
        for a in model.aliases:
            if a and a.upper() != model.model_key.upper():
                terms.append(a)
        return terms[:2]
