"""Capture a dated cross-shop price snapshot for the browsable ranking page.

    python tools/artifact/export_prices.py            # live scan of the six shops
    python tools/artifact/export_prices.py --from-db  # last stored run instead of a live scan

Writes tools/artifact/prices.json, which build_page.py embeds in ranking.html.

The page is static and the scrapers cannot run in a browser, so what it carries is a reading taken at
one moment, not a live feed. Everything written here is stamped with the time it was taken and the
page presents it as frozen. The dashboard on the laptop remains the only live answer.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from monbot import config as config_mod          # noqa: E402
from monbot import criteria as criteria_mod      # noqa: E402
from monbot import watchlist as watchlist_mod    # noqa: E402
from monbot.compare import group_items           # noqa: E402
from monbot.engine import shop_labels            # noqa: E402
from monbot.models import Item                   # noqa: E402
from monbot.shops import SHOPS                   # noqa: E402
from monbot.store import Store                   # noqa: E402


def live_items(cfg: dict, models) -> tuple[list[Item], list[str]]:
    from monbot.fetch import Fetcher
    fetch_cfg = cfg.get("fetch", {})
    fetcher = Fetcher(timeout=float(fetch_cfg.get("timeout_s", 40)),
                      pause=float(fetch_cfg.get("pause_s", 1.0)),
                      playwright_mode=fetch_cfg.get("playwright", "auto"))
    items: list[Item] = []
    failed: list[str] = []
    try:
        for name, cls in SHOPS.items():
            if not cfg.get("shops", {}).get(name, True):
                continue
            print(f"  scanning {cls.label}…", file=sys.stderr)
            try:
                items.extend(cls(fetcher).fetch_items(models))
            except Exception as e:
                failed.append(name)
                print(f"  {name} failed: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        fetcher.close()
    return items, failed


def db_items() -> tuple[list[Item], list[str]]:
    rows = Store().current_offers()
    return [Item(shop=r["shop"], title=r["title"], price=r["price"], url=r["url"],
                 list_price=r["list_price"],
                 in_stock=None if r["in_stock"] is None else bool(r["in_stock"]),
                 shop_sku=r["shop_sku"] or "") for r in rows], []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-db", action="store_true", help="use the last stored run, not a live scan")
    args = ap.parse_args()

    cfg = config_mod.load()
    crit = criteria_mod.from_config(cfg)
    wl = watchlist_mod.load()
    models = wl.watched(crit)

    items, failed = db_items() if args.from_db else live_items(cfg, models)
    groups = group_items(items, models, crit, wl.rejected)

    out = {
        "as_of": datetime.now().isoformat(timespec="minutes"),
        "source": "stored run" if args.from_db else "live scan",
        "shops": shop_labels(),
        "failed_shops": failed,
        "currency": "EUR",
        "criteria_label": crit.label,
        "groups": [{
            "key": g.key,
            "label": g.label,
            "confident": g.confident,
            "model_key": g.model.model_key if g.model else None,
            "spread_pct": None if g.spread_pct is None else round(g.spread_pct, 1),
            "offers": [{"shop": o.shop, "price": o.price, "list_price": o.list_price,
                        "in_stock": o.in_stock, "url": o.url, "title": o.title}
                       for o in g.ranked],
        } for g in groups if g.ranked],
    }
    # the cheapest in-stock price per watched model, which is what the value score divides by
    out["best_prices"] = {g["model_key"]: g["offers"][0]["price"]
                          for g in out["groups"] if g["model_key"] and g["offers"]}

    path = HERE / "prices.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    multi = sum(1 for g in out["groups"] if len(g["offers"]) > 1)
    print(f"{path}: {len(out['groups'])} products, {multi} at two or more shops, "
          f"{len(out['best_prices'])} watched models priced, as of {out['as_of']}"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
