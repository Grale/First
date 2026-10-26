"""One price check: fetch shops -> match watchlist -> store -> rules -> notify."""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from . import config as config_mod
from . import criteria as criteria_mod
from . import watchlist as watchlist_mod
from . import notify, rules
from .fetch import Fetcher
from .criteria import Criteria
from .match import best_match, looks_like_candidate, matches_rejected
from .models import Item, Offer, Alert
from .shops import SHOPS, shop_country
from .store import Store

log = logging.getLogger("soundbot.engine")


@dataclass
class ShopResult:
    shop: str
    ok: bool
    n_items: int = 0
    n_offers: int = 0
    tier: str = ""
    error: str = ""
    seconds: float = 0.0


@dataclass
class RunResult:
    run_id: int
    dry_run: bool
    shops: list[ShopResult] = field(default_factory=list)
    offers: list[Offer] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    sent: list[tuple[Alert, list[str]]] = field(default_factory=list)
    unmatched: list[Item] = field(default_factory=list)

    @property
    def summary(self) -> str:
        ok = [s.shop for s in self.shops if s.ok]
        bad = [f"{s.shop} ({s.error[:60]})" for s in self.shops if not s.ok]
        parts = [f"{len(self.offers)} offers from {len(ok)} shops"]
        if bad:
            parts.append("failed: " + ", ".join(bad))
        parts.append(f"{len(self.alerts)} alerts, {len(self.sent)} sent")
        return "; ".join(parts)


def shop_labels() -> dict[str, str]:
    return {name: cls.label for name, cls in SHOPS.items()}


def enabled_shops(cfg: dict) -> list[str]:
    """Shops switched on, in a country that is switched on."""
    shops = cfg.get("shops", {})
    countries = cfg.get("countries", {})
    return [n for n, cls in SHOPS.items()
            if shops.get(n, True) and countries.get(cls.country, True)]


def match_items(items: list[Item], models, price_range: dict, crit: Criteria,
                rejected=()) -> tuple[list[Offer], list[Item]]:
    lo = float(price_range.get("min", 0) or 0)
    hi = float(price_range.get("max", 10 ** 9) or 10 ** 9)
    offers: list[Offer] = []
    unmatched: list[Item] = []
    for it in items:
        m = best_match(it.title, models, crit, rejected)
        if m is None:
            if (looks_like_candidate(it.title, crit) and (it.price is None or lo <= it.price <= hi)
                    and not matches_rejected(it.title, rejected, crit)):
                unmatched.append(it)
            continue
        if it.price is not None and not (lo <= it.price <= hi):
            log.info("skip %s %s: price %.2f outside range", it.shop, it.title, it.price)
            continue
        list_price = it.list_price
        if list_price and it.price and (list_price > it.price * 2.5 or list_price <= it.price):
            list_price = None   # shop data error (e.g. a list price of 3,490 for a 349 bar)
        offers.append(Offer(shop=it.shop, model_key=m.model_key, title=it.title, price=it.price, url=it.url,
                            list_price=list_price, in_stock=it.in_stock, shop_sku=it.shop_sku))
    return offers, unmatched


def previous_state(store: Store, before_run: int) -> dict[tuple[str, str], Offer]:
    """Latest successful snapshot per shop before this run, as {(shop, model_key): Offer}."""
    prev: dict[tuple[str, str], Offer] = {}
    for shop in SHOPS:
        rid = store.last_ok_run_for_shop(shop, before_run=before_run)
        if rid is None:
            continue
        for row in store.offers_for_run(rid, shop=shop):
            key = (row["shop"], row["model_key"])
            o = Offer(shop=row["shop"], model_key=row["model_key"], title=row["title"], price=row["price"],
                      url=row["url"], list_price=row["list_price"],
                      in_stock=None if row["in_stock"] is None else bool(row["in_stock"]),
                      shop_sku=row["shop_sku"] or "", seen_at=row["seen_at"])
            if key not in prev or (o.price or 1e9) < (prev[key].price or 1e9):
                prev[key] = o
    return prev


def run_check(store: Store, dry_run: bool = False, only_shops: Optional[list[str]] = None,
              progress=None) -> RunResult:
    cfg = config_mod.load()
    wl = watchlist_mod.load()
    crit = criteria_mod.from_config(cfg)
    models = wl.watched(crit)
    labels = shop_labels()
    run_id = store.start_run(dry_run=dry_run)
    result = RunResult(run_id=run_id, dry_run=dry_run)
    fetch_cfg = cfg.get("fetch", {})
    fetcher = Fetcher(timeout=float(fetch_cfg.get("timeout_s", 40)), pause=float(fetch_cfg.get("pause_s", 1.0)),
                      playwright_mode=fetch_cfg.get("playwright", "auto"))
    wanted = only_shops or enabled_shops(cfg)
    prev = previous_state(store, before_run=run_id)
    try:
        for name, cls in SHOPS.items():
            if name not in wanted:
                continue
            if progress:
                progress(f"checking {cls.label}…")
            t0 = time.monotonic()
            shop = cls(fetcher)
            sr = ShopResult(shop=name, ok=False)
            try:
                items = shop.fetch_items(models)
                offers, unmatched = match_items(items, models, cfg.get("price_range", {}), crit, wl.rejected)
                sr.ok, sr.n_items, sr.n_offers = True, len(items), len(offers)
                store.add_offers(run_id, offers)   # persist per shop, so an interrupted run keeps what it got
                result.offers.extend(offers)
                result.unmatched.extend(unmatched)
                log.info("%s: %d items, %d matched", name, len(items), len(offers))
            except Exception as e:
                sr.error = f"{type(e).__name__}: {e}"
                log.exception("%s failed", name)
            sr.seconds = round(time.monotonic() - t0, 1)
            sr.tier = fetcher.tier_used.get(cls.base_url.split("/")[2], "")
            result.shops.append(sr)
            store.record_shop_run(run_id, name, sr.ok, sr.n_items, sr.n_offers, sr.tier, sr.error, sr.seconds)
    finally:
        fetcher.close()

    # rules run on the merged current state: this run's offers, plus the last good snapshot of shops that
    # failed now or were not checked
    failed = {s.shop for s in result.shops if not s.ok}
    skipped = {n for n in SHOPS if not any(s.shop == n for s in result.shops)}
    current = list(result.offers)
    for (shop, _mk), o in prev.items():
        if shop in failed or shop in skipped:
            current.append(o)
    alerts = rules.evaluate(current, prev, wl, cfg, labels)
    alerts = [a for a in alerts if a.shop not in failed]   # never alert on stale data of a failed shop
    result.alerts = rules.filter_dedupe(alerts, store, int(cfg.get("rules", {}).get("dedupe_days", 7)))

    if not dry_run:
        for a in result.alerts:
            channels = notify.send_alert(cfg, a)
            store.add_alert(a, ",".join(channels))
            result.sent.append((a, channels))
    store.finish_run(run_id, notes=result.summary)
    log.info("run %s done: %s", run_id, result.summary)
    return result


def discover(only_shops: Optional[list[str]] = None, progress=None) -> dict[str, list[Item]]:
    """Soundbar titles that fit the criteria but match no watchlist model."""
    cfg = config_mod.load()
    wl = watchlist_mod.load()
    crit = criteria_mod.from_config(cfg)
    models = wl.models
    fetch_cfg = cfg.get("fetch", {})
    fetcher = Fetcher(timeout=float(fetch_cfg.get("timeout_s", 40)), pause=float(fetch_cfg.get("pause_s", 1.0)),
                      playwright_mode=fetch_cfg.get("playwright", "auto"))
    wanted = only_shops or enabled_shops(cfg)
    out: dict[str, list[Item]] = {}
    try:
        for name, cls in SHOPS.items():
            if name not in wanted:
                continue
            if progress:
                progress(f"scanning {cls.label}…")
            shop = cls(fetcher)
            try:
                items = shop.fetch_all_bars()
            except Exception as e:
                out[name] = [Item(shop=name, title=f"[scan failed: {e}]", price=None, url="")]
                continue
            found: list[Item] = []
            for it in items:
                if not looks_like_candidate(it.title, crit):
                    continue
                if best_match(it.title, models, crit, wl.rejected) is not None:
                    continue
                if matches_rejected(it.title, wl.rejected, crit):
                    continue
                found.append(it)
            out[name] = found
    finally:
        fetcher.close()
    return out


def country_of(shop: str) -> str:
    return shop_country(shop)
