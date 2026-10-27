"""Cross-shop price comparison for everything the shops sell at the wanted size.

The dashboard compares prices for models on the watch list. This compares prices for every monitor the
six shops carry that fits the size criteria, watched or not, which is a different and larger question:
the watch list holds twelve models and only two of them are stocked in Cyprus, while the shops between
them carry dozens the list has never heard of. A model has to be recognised across shops before its
prices can be compared, and the shops do not agree on how to write one:

    SAMSUNG LS34DG850SUXDU Curved Gaming PC Monitor, 34"                        (Electroline)
    Samsung LS34DG850SUXDU 34" UWQHD OLED 175Hz                                 (Kotsovolos)
    PC Monitor 34" SAMSUNG Curved Odyssey G8 G85SD LS34DG850SUXDU Ultra WQHD    (Stephanis)

A watch-list model is identified by the matcher, which is authoritative. Everything else is grouped by
its model code: the longest token carrying both letters and digits, truncated to drop the regional
suffix that differs between shops selling the same panel (…SUXDU against …SUXEN). That truncation is a
heuristic and it can be wrong, so `confident` marks which groups came from the matcher instead.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .criteria import Criteria
from .match import best_match, looks_like_candidate, normalize
from .models import Item
from .watchlist import Model, Rejected

# Where a model code is truncated for grouping. Nine characters keeps LS34BG850 apart from LS34DG850
# (one character, several hundred euros) while still joining LS34DG850SUXDU to LS34DG850SUXEN.
CODE_PREFIX = 9
MIN_CODE = 5


def model_code(title: str) -> Optional[str]:
    """The longest token in a title that carries both letters and digits: its model code."""
    tokens = [t for t in normalize(title).split()
              if len(t) >= MIN_CODE and any(c.isalpha() for c in t) and any(c.isdigit() for c in t)]
    return max(tokens, key=len) if tokens else None


@dataclass
class Group:
    key: str
    label: str
    confident: bool = False          # identified by the matcher rather than by a code prefix
    model: Optional[Model] = None
    items: list[Item] = field(default_factory=list)

    @property
    def per_shop(self) -> dict[str, Item]:
        """The cheapest in-stock listing in each shop."""
        out: dict[str, Item] = {}
        for it in sorted([i for i in self.items if i.price], key=lambda i: i.price):
            if it.in_stock is False:
                continue
            out.setdefault(it.shop, it)
        return out

    @property
    def ranked(self) -> list[Item]:
        return sorted(self.per_shop.values(), key=lambda i: i.price)

    @property
    def cheapest(self) -> Optional[Item]:
        r = self.ranked
        return r[0] if r else None

    @property
    def dearest(self) -> Optional[Item]:
        r = self.ranked
        return r[-1] if r else None

    @property
    def spread_pct(self) -> Optional[float]:
        """How much more the dearest shop asks than the cheapest, as a percentage of the cheapest."""
        if len(self.ranked) < 2:
            return None
        lo, hi = self.cheapest.price, self.dearest.price
        return (hi / lo - 1) * 100 if lo else None


def group_items(items: Iterable[Item], models: list[Model], crit: Criteria,
                rejected: Iterable[Rejected] = (),
                price_range: Optional[dict] = None) -> list[Group]:
    """Group everything that fits the size criteria by the product it is, cheapest spread first.

    The price range is the same shop-data-error filter the engine applies. It earns its keep here too:
    a search for "Epson 34" returns ink cartridges at 13 EUR, which carry a standalone 34 and are not
    monitors by any test this module can make.
    """
    lo = float((price_range or {}).get("min", 0) or 0)
    hi = float((price_range or {}).get("max", 10 ** 9) or 10 ** 9)
    groups: dict[str, Group] = {}
    for it in items:
        if it.price is not None and not (lo <= it.price <= hi):
            continue
        # check_panel=False on purpose: see looks_like_candidate. The comparison must see every
        # listing of a product, including the shops whose titles name a panel family the buyer has
        # ruled out, or it reports the wrong number of shops and the wrong spread.
        if not it.price or not looks_like_candidate(it.title, crit, check_panel=False):
            continue
        m = best_match(it.title, models, crit, rejected)
        if m is not None:
            key, label, confident = m.model_key.upper(), m.display_name, True
        else:
            code = model_code(it.title)
            if not code:
                continue
            key = code[:CODE_PREFIX]
            label, confident = code, False
        g = groups.get(key)
        if g is None:
            g = groups[key] = Group(key=key, label=label, confident=confident, model=m)
        elif confident and not g.confident:
            g.label, g.confident, g.model = label, True, m
        g.items.append(it)

    out = list(groups.values())
    out.sort(key=lambda g: (-(g.spread_pct or -1), g.cheapest.price if g.cheapest else 0))
    return out
