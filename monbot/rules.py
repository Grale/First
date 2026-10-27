"""Alert rules evaluated on the current snapshot.

cross_shop     one shop's price is at least X% below the second-lowest shop for the same model
list_discount  a shop's price is at least Y% below its own list (strikethrough) price
back_in_stock  a (shop, model) that was out of stock / absent in the previous successful snapshot is now in stock
"""
from __future__ import annotations
from collections import defaultdict
from typing import Optional

from .models import Offer, Alert
from .store import Store
from .watchlist import Watchlist


def _fmt(p: Optional[float]) -> str:
    return "n/a" if p is None else f"€{p:,.2f}"


def _label(shop: str, labels: dict[str, str]) -> str:
    return labels.get(shop, shop)


def evaluate(current: list[Offer], previous: dict[tuple[str, str], Offer], wl: Watchlist, cfg: dict,
             labels: dict[str, str]) -> list[Alert]:
    rules = cfg.get("rules", {})
    cross_pct = float(rules.get("cross_shop_pct", 10))
    disc_pct = float(rules.get("list_discount_pct", 20))
    want_restock = bool(rules.get("back_in_stock", True))
    alerts: list[Alert] = []

    by_model: dict[str, list[Offer]] = defaultdict(list)
    for o in current:
        by_model[o.model_key].append(o)

    for model_key, offers in by_model.items():
        model = wl.get(model_key)
        prio = bool(model and model.priority)
        name = model.display_name if model else model_key
        priced = [o for o in offers if o.price and o.in_stock is not False]   # out-of-stock prices are not offers
        # one entry per shop: the cheapest listing of that model in the shop
        per_shop: dict[str, Offer] = {}
        for o in sorted(priced, key=lambda x: x.price):
            per_shop.setdefault(o.shop, o)
        ranked = sorted(per_shop.values(), key=lambda x: x.price)

        # 1) cross-shop
        if len(ranked) >= 2:
            low, second = ranked[0], ranked[1]
            if low.price <= second.price * (1 - cross_pct / 100):
                saving = (1 - low.price / second.price) * 100
                others = ", ".join(f"{_label(o.shop, labels)} {_fmt(o.price)}" for o in ranked[1:4])
                alerts.append(Alert(
                    rule="cross_shop", shop=low.shop, model_key=model_key, price=low.price, title=low.title,
                    message=f"{name}: {_label(low.shop, labels)} {_fmt(low.price)} is {saving:.0f}% below {others}",
                    url=low.url, dedupe_key=f"cross_shop|{low.shop}|{model_key}|{low.price:.2f}", priority=prio))

        # 2) list discount
        for o in ranked:
            if o.list_price and o.price and o.price <= o.list_price * (1 - disc_pct / 100):
                pct = (1 - o.price / o.list_price) * 100
                alerts.append(Alert(
                    rule="list_discount", shop=o.shop, model_key=model_key, price=o.price, title=o.title,
                    message=f"{name}: {_label(o.shop, labels)} {_fmt(o.price)}, {pct:.0f}% off list {_fmt(o.list_price)}",
                    url=o.url, dedupe_key=f"list_discount|{o.shop}|{model_key}|{o.price:.2f}", priority=prio))

        # 3) back in stock
        if want_restock:
            for o in per_shop.values():
                prev = previous.get((o.shop, model_key))
                was_available = prev is not None and prev.in_stock is not False
                if o.in_stock and prev is not None and not was_available:
                    alerts.append(Alert(
                        rule="back_in_stock", shop=o.shop, model_key=model_key, price=o.price, title=o.title,
                        message=f"{name}: back in stock at {_label(o.shop, labels)} for {_fmt(o.price)}",
                        url=o.url, dedupe_key=f"back_in_stock|{o.shop}|{model_key}", priority=prio))
    return alerts


def filter_dedupe(alerts: list[Alert], store: Store, days: int) -> list[Alert]:
    """Drop alerts already sent recently, unless the price got lower than the last alerted price."""
    out: list[Alert] = []
    for a in alerts:
        if store.alert_sent_recently(a.dedupe_key, days):
            continue
        last = store.last_alert_price(a.rule, a.shop, a.model_key)
        if a.rule in ("cross_shop", "list_discount") and last is not None and a.price is not None:
            if a.price >= last and store.alert_sent_recently(f"{a.rule}|{a.shop}|{a.model_key}|{last:.2f}", days):
                continue
        out.append(a)
    return out
