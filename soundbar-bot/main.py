"""Soundbar Deal Bot command line.

  python main.py serve                 start the dashboard + background checks (what Task Scheduler runs)
  python main.py run-once [--dry-run] [--shop NAME ...] [--country CY|GR]
  python main.py report
  python main.py discover [--shop NAME ...]
  python main.py test-notify
  python main.py install-task | uninstall-task | task-status | task-run | task-restart
  python main.py validate              check watchlist.json against the criteria
"""
from __future__ import annotations
import argparse
import sys
import webbrowser

from soundbot import config as config_mod
from soundbot import criteria as criteria_mod
from soundbot import watchlist as watchlist_mod
from soundbot.logsetup import setup as log_setup
from soundbot.shops import COUNTRIES, SHOPS, shop_country, shops_in
from soundbot.store import Store


def _print(*a):
    try:
        print(*a)
    except UnicodeEncodeError:
        print(*(str(x).encode("ascii", "replace").decode() for x in a))


def _only_shops(args) -> list[str] | None:
    shops = list(args.shop or [])
    for c in args.country or []:
        shops.extend(s for s in shops_in(c.upper()) if s not in shops)
    return shops or None


def cmd_run_once(args) -> int:
    from soundbot.engine import run_check
    store = Store()
    res = run_check(store, dry_run=args.dry_run, only_shops=_only_shops(args),
                    progress=lambda m: _print("  ", m))
    _print(f"\nrun #{res.run_id} {'(dry run) ' if res.dry_run else ''}{res.summary}")
    for s in res.shops:
        flag = "ok " if s.ok else "ERR"
        _print(f"  {flag} {s.shop:<14} items={s.n_items:<4} matched={s.n_offers:<3} "
               f"tier={s.tier or '-':<10} {s.seconds}s {s.error}")
    if res.offers:
        _print("\nmatched offers:")
        for o in sorted(res.offers, key=lambda x: (x.model_key, x.price or 1e9)):
            stock = "in stock" if o.in_stock else ("?" if o.in_stock is None else "OUT")
            lp = f" (list €{o.list_price:,.2f})" if o.list_price else ""
            _print(f"  {o.model_key:<22} {o.shop:<14} €{(o.price or 0):>9,.2f}{lp:<18} {stock:<9} "
                   f"{o.title[:60]}")
    if res.unmatched:
        _print("\nsoundbars that fit the criteria but match no watchlist model:")
        for it in res.unmatched[:40]:
            _print(f"  {it.shop:<14} €{(it.price or 0):>9,.2f}  {it.title[:90]}")
    if res.alerts:
        _print("\nalerts" + (" (would send)" if res.dry_run else ""))
        for a in res.alerts:
            _print(f"  [{a.rule}] {a.message}")
    return 0


def cmd_report(args) -> int:
    from soundbot.scoring import rank_models
    store = Store()
    wl = watchlist_mod.load()
    rows = store.current_offers()
    by_model: dict[str, list] = {}
    for r in rows:
        by_model.setdefault(r["model_key"], []).append(r)
    cfg = config_mod.load()
    best_prices = {}
    for mk, rs in by_model.items():
        p = [r["price"] for r in rs if r["price"] and r["in_stock"] != 0]
        if p:
            best_prices[mk] = min(p)
    _print(f"{'#':<3}{'model':<30} {'score':<18} {'system':<30} {'cheapest':<26} offers")
    for rank, m, sc in rank_models(wl.models, cfg, best_prices):
        offers = sorted([r for r in by_model.get(m.model_key, []) if r["price"]], key=lambda r: r["price"])
        system = f"{m.specs.layout} {m.specs.subwoofer.replace('_', ' ')}"
        cheapest = (f"{offers[0]['shop']} €{offers[0]['price']:,.2f} "
                    f"({shop_country(offers[0]['shop'])})") if offers else "-"
        rest = ", ".join(f"{r['shop']}:{r['price']:,.0f}" for r in offers)
        star = "*" if m.priority else " "
        score = (f"{sc.overall} (f{sc.fit:.0f}/r{sc.review:.0f})" if sc.has_review
                 else f"{sc.overall} (f{sc.fit:.0f}/no rev)")
        _print(f"{rank:<3}{star}{m.display_name[:29]:<29} {score:<18} {system:<30} {cheapest:<26} {rest}")
    _print(f"\n{len(rows)} current offers; last runs:")
    for r in store.last_runs(5):
        _print(f"  #{r['id']} {r['started_at']} {'dry ' if r['dry_run'] else ''}{r['notes']}")
    return 0


def cmd_discover(args) -> int:
    from soundbot.engine import discover
    out = discover(only_shops=_only_shops(args), progress=lambda m: _print("  ", m))
    total = 0
    for shop, items in out.items():
        _print(f"\n{shop}: {len(items)} soundbars not on the watchlist")
        for it in items:
            total += 1
            _print(f"  €{(it.price or 0):>9,.2f}  {it.title[:100]}  {it.url}")
    _print(f"\n{total} titles not on the watchlist")
    return 0


def cmd_probe(args) -> int:
    """Show what one shop returns and where each listing is lost, item by item.

    A shop that reports a lot of items and few matches is doing one of four things, and this says
    which: returning products that are not soundbars, returning soundbars whose title prints no
    height channels, returning the right product under a title the aliases do not cover, or pricing
    it outside the range.
    """
    from soundbot.criteria import looks_like_soundbar, parse_layout
    from soundbot.fetch import Fetcher
    from soundbot.match import best_match, matches_rejected

    cfg = config_mod.load()
    crit = criteria_mod.from_config(cfg)
    wl = watchlist_mod.load()
    models = wl.watched(crit)
    if args.model:
        wanted = [m for m in models if args.model.upper() in m.model_key.upper()]
        if not wanted:
            _print(f"no watched model matches {args.model!r}")
            return 1
        models = wanted
    lo = float(cfg["price_range"]["min"])
    hi = float(cfg["price_range"]["max"])

    fetch_cfg = cfg.get("fetch", {})
    fetcher = Fetcher(timeout=float(fetch_cfg.get("timeout_s", 40)),
                      pause=float(fetch_cfg.get("pause_s", 1.0)),
                      playwright_mode=fetch_cfg.get("playwright", "auto"))
    shop = SHOPS[args.shop](fetcher)
    _print(f"probing {shop.label} with {len(models)} model(s)…")
    try:
        items = shop.fetch_items(models)
    except Exception as e:
        # A probe reports; it does not re-raise a wall of traceback at someone who asked a question.
        _print(f"\n{shop.label} could not be read:\n  {type(e).__name__}: {e}")
        return 1
    finally:
        fetcher.close()

    def verdict(it) -> str:
        m = best_match(it.title, models, crit, wl.rejected)
        if m is not None:
            if it.price is not None and not (lo <= it.price <= hi):
                return f"PRICED OUT  would match {m.model_key}, €{it.price:,.2f} outside €{lo:,.0f}-€{hi:,.0f}"
            return f"MATCH       {m.model_key}"
        if matches_rejected(it.title, wl.rejected, crit):
            return "rejected    a checked-and-rejected model"
        if not looks_like_soundbar(it.title):
            return "not a bar   no soundbar word in the title, or it reads as a component"
        layout = parse_layout(it.title)
        if layout is None:
            if "ATMOS" in it.title.upper():
                return "CANDIDATE   claims Atmos, no layout printed"
            return "no layout   no channel layout and no Atmos claim in the title"
        if layout[2] < crit.min_height_channels:
            return f"no height   title prints {layout[0]}.{layout[1]}.{layout[2]}"
        return f"CANDIDATE   {layout[0]}.{layout[1]}.{layout[2]}, not on the watchlist"

    counts: dict[str, int] = {}
    _print(f"\n{len(items)} items returned\n")
    for it in items[:args.limit]:
        v = verdict(it)
        counts[v.split()[0]] = counts.get(v.split()[0], 0) + 1
        _print(f"  {v[:58]:<58} €{(it.price or 0):>8,.2f}  {it.title[:70]}")
    if len(items) > args.limit:
        for it in items[args.limit:]:
            v = verdict(it)
            counts[v.split()[0]] = counts.get(v.split()[0], 0) + 1
        _print(f"  … {len(items) - args.limit} more not printed")
    _print("\nsummary: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


def cmd_test_notify(args) -> int:
    from soundbot import notify
    cfg = config_mod.load()
    sent = notify.send(cfg, "Soundbar Deal Bot test",
                       "Notifications are working. Topic: " + cfg["notify"]["ntfy"]["topic"],
                       url="http://%s:%d/" % (cfg["ui"]["host"], int(cfg["ui"]["port"])))
    _print("sent via:", ", ".join(sent) or "nothing (check config)")
    return 0 if sent else 1


def cmd_validate(args) -> int:
    wl = watchlist_mod.load()
    crit = criteria_mod.active()
    cfg = config_mod.load()
    problems = wl.validate(crit)
    _print(f"criteria: {crit.label}")
    _print(f"{len(wl.models)} models ({len(wl.watched(crit))} watched), {len(wl.rejected)} rejected")
    for code, name in COUNTRIES.items():
        on = [s for s in shops_in(code) if cfg["shops"].get(s, True)]
        state = "on" if cfg.get("countries", {}).get(code, True) else "off"
        _print(f"  {name} ({state}): {', '.join(on) or 'no shops enabled'}")
    for p in problems:
        _print("  !", p)
    return 1 if problems else 0


def cmd_serve(args) -> int:
    from soundbot.scheduler import Scheduler
    from soundbot.web.app import create_app
    cfg = config_mod.load()
    store = Store()
    sched = Scheduler(store)
    sched.start()
    app = create_app(store, sched)
    host, port = cfg["ui"]["host"], int(cfg["ui"]["port"])
    _print(f"Soundbar Deal Bot dashboard: http://{host}:{port}")
    if args.open:
        webbrowser.open(f"http://{host}:{port}")
    try:
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
    finally:
        sched.stop()
    return 0


def cmd_task(args, action: str) -> int:
    from soundbot import tasksched
    fn = {"install": tasksched.install, "uninstall": tasksched.uninstall,
          "status": tasksched.query, "run": tasksched.run_task, "restart": tasksched.restart_task}[action]
    _print(fn())
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="soundbot", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_shop_args(parser):
        parser.add_argument("--shop", action="append", choices=list(SHOPS), help="limit to these shops")
        parser.add_argument("--country", action="append", choices=list(COUNTRIES),
                            help="limit to the shops in this country")

    s = sub.add_parser("run-once", help="run one price check now")
    s.add_argument("--dry-run", action="store_true", help="evaluate rules but send nothing")
    add_shop_args(s)
    s.set_defaults(fn=cmd_run_once)

    s = sub.add_parser("report", help="print current prices per model and shop")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("discover", help="soundbars in the shops that fit the criteria but are not watched")
    add_shop_args(s)
    s.set_defaults(fn=cmd_discover)

    s = sub.add_parser("probe", help="show what one shop returns and where each listing is lost")
    s.add_argument("--shop", required=True, choices=list(SHOPS))
    s.add_argument("--model", help="query for this model only (substring of a model key)")
    s.add_argument("--limit", type=int, default=40, help="how many items to print (default 40)")
    s.set_defaults(fn=cmd_probe)

    s = sub.add_parser("test-notify", help="send a test toast and ntfy push")
    s.set_defaults(fn=cmd_test_notify)

    s = sub.add_parser("validate", help="validate watchlist.json against the criteria")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("serve", help="start the dashboard and background checks")
    s.add_argument("--open", action="store_true", help="open the dashboard in the browser")
    s.set_defaults(fn=cmd_serve)

    for action in ("install", "uninstall", "status", "run"):
        s = sub.add_parser(f"{action}-task" if action != "status" else "task-status",
                           help=f"{action} the Windows scheduled task")
        s.set_defaults(fn=lambda a, _act=action: cmd_task(a, _act))
    sub._name_parser_map["task-run"] = sub._name_parser_map.pop("run-task")
    s_restart = sub.add_parser("task-restart", help="restart the background server after code or config changes")
    s_restart.set_defaults(fn=lambda a: cmd_task(a, "restart"))

    args = p.parse_args(argv)
    log_setup(console=args.cmd != "serve")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
