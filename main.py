"""Monitor Deal Bot command line.

  python main.py serve                 start the dashboard + background checks (what Task Scheduler runs)
  python main.py run-once [--dry-run] [--shop NAME ...]
  python main.py report
  python main.py discover [--shop NAME ...]
  python main.py check-shops [--shop NAME ...]   confirm each shop's monitor category is reachable
  python main.py compare [--min-shops N]         cross-shop price comparison for every monitor at this size
  python main.py test-notify
  python main.py install-task | uninstall-task | task-status | task-run | task-restart
  python main.py validate              check watchlist.json
"""
from __future__ import annotations
import argparse
import sys
import webbrowser

from monbot import config as config_mod
from monbot import criteria as criteria_mod
from monbot import watchlist as watchlist_mod
from monbot.logsetup import setup as log_setup
from monbot.match import looks_like_candidate
from monbot.shops import SHOPS
from monbot.store import Store


def _print(*a):
    try:
        print(*a)
    except UnicodeEncodeError:
        print(*(str(x).encode("ascii", "replace").decode() for x in a))


def cmd_run_once(args) -> int:
    from monbot.engine import run_check
    store = Store()
    res = run_check(store, dry_run=args.dry_run, only_shops=args.shop or None, progress=lambda m: _print("  ", m))
    _print(f"\nrun #{res.run_id} {'(dry run) ' if res.dry_run else ''}{res.summary}")
    for s in res.shops:
        flag = "ok " if s.ok else "ERR"
        _print(f"  {flag} {s.shop:<12} items={s.n_items:<4} matched={s.n_offers:<3} tier={s.tier or '-':<10} {s.seconds}s {s.error}")
    if res.offers:
        _print("\nmatched offers:")
        for o in sorted(res.offers, key=lambda x: (x.model_key, x.price or 1e9)):
            stock = "in stock" if o.in_stock else ("?" if o.in_stock is None else "OUT")
            lp = f" (list €{o.list_price:,.2f})" if o.list_price else ""
            _print(f"  {o.model_key:<14} {o.shop:<12} €{(o.price or 0):>9,.2f}{lp:<18} {stock:<9} {o.title[:70]}")
    if res.unmatched:
        _print(f"\nunmatched {criteria_mod.active().label} titles (candidates for the watchlist):")
        for it in res.unmatched[:40]:
            _print(f"  {it.shop:<12} €{(it.price or 0):>9,.2f}  {it.title[:90]}")
    if res.alerts:
        _print("\nalerts" + (" (would send)" if res.dry_run else ""))
        for a in res.alerts:
            _print(f"  [{a.rule}] {a.message}")
    return 0


def cmd_report(args) -> int:
    store = Store()
    wl = watchlist_mod.load()
    rows = store.current_offers()
    by_model: dict[str, list] = {}
    for r in rows:
        by_model.setdefault(r["model_key"], []).append(r)
    from monbot.scoring import rank_models
    cfg = config_mod.load()
    best_prices = {}
    for mk, rs in by_model.items():
        p = [r["price"] for r in rs if r["price"] and r["in_stock"] != 0]
        if p:
            best_prices[mk] = min(p)
    _print(f"{'#':<3}{'model':<34} {'score':<18} {'specs':<34} {'cheapest':<30} offers")
    for rank, m, sc in rank_models(wl.models, cfg, best_prices):
        offers = sorted([r for r in by_model.get(m.model_key, []) if r["price"]], key=lambda r: r["price"])
        pd = f"{m.specs.usb_c_pd_w}W" if m.specs.usb_c_pd_w else "-"
        specs = f"{m.specs.hz}Hz {m.resolution_label} PD={pd} KVM={'y' if m.specs.kvm else 'n'}"
        cheapest = f"{offers[0]['shop']} €{offers[0]['price']:,.2f}" if offers else "-"
        rest = ", ".join(f"{r['shop']}:{r['price']:,.0f}" for r in offers)
        star = "*" if m.priority else " "
        score = f"{sc.overall} (f{sc.fit:.0f}/r{sc.review:.0f})" if sc.has_review else f"{sc.overall} (f{sc.fit:.0f}/no rev)"
        _print(f"{rank:<3}{star}{m.display_name:<33} {score:<18} {specs:<34} {cheapest:<30} {rest}")
    _print(f"\n{len(rows)} current offers; last runs:")
    for r in store.last_runs(5):
        _print(f"  #{r['id']} {r['started_at']} {'dry ' if r['dry_run'] else ''}{r['notes']}")
    return 0


def cmd_discover(args) -> int:
    from monbot.engine import discover
    crit = criteria_mod.active()
    out = discover(only_shops=args.shop or None, progress=lambda m: _print("  ", m))
    total = 0
    for shop, items in out.items():
        _print(f"\n{shop}: {len(items)} unmatched {crit.label} titles")
        for it in items:
            total += 1
            _print(f"  €{(it.price or 0):>9,.2f}  {it.title[:100]}  {it.url}")
    _print(f"\n{total} titles not on the watchlist")
    return 0


def cmd_compare(args) -> int:
    """Price the same monitor across every shop that carries it, watched or not."""
    from monbot.compare import group_items
    from monbot.engine import shop_labels
    from monbot.fetch import Fetcher
    from monbot.shops import SHOPS
    cfg = config_mod.load()
    crit = criteria_mod.from_config(cfg)
    wl = watchlist_mod.load()
    models = wl.watched(crit)
    fetch_cfg = cfg.get("fetch", {})
    fetcher = Fetcher(timeout=float(fetch_cfg.get("timeout_s", 40)), pause=float(fetch_cfg.get("pause_s", 1.0)),
                      playwright_mode=fetch_cfg.get("playwright", "auto"))
    items, failed = [], []
    try:
        for name, cls in SHOPS.items():
            if not cfg.get("shops", {}).get(name, True):
                continue
            _print("  ", f"scanning {cls.label}…")
            try:
            # fetch_all_products(), not fetch_items(models): the search-driven shops query once per
            # watchlist model, so a narrower watch list would silently narrow the market survey too.
            # Kotsovolos returned 111 products against a twelve-model list and 43 against a three-model
            # one, for no reason connected to what the shops actually stock.
                items.extend(cls(fetcher).fetch_all_products())
            except Exception as e:
                failed.append(f"{name} ({type(e).__name__})")
    finally:
        fetcher.close()

    groups = group_items(items, models, crit, wl.rejected, cfg.get("price_range"))
    multi = [g for g in groups if len(g.ranked) >= args.min_shops]
    labels = shop_labels()

    _print(f"\n{crit.label}: {len(groups)} distinct products across {len(SHOPS) - len(failed)} shops"
           + (f"; failed: {', '.join(failed)}" if failed else ""))
    _print(f"{len(multi)} sold by {args.min_shops} or more shops\n")
    def row(g) -> str:
        lo = g.cheapest
        star = "*" if g.confident else " "
        name = g.label if len(g.label) <= 36 else g.label[:35] + "\u2026"
        cheapest = f"{labels.get(lo.shop, lo.shop)} EUR {lo.price:,.2f}"
        spread = f"+{g.spread_pct:.0f}%" if g.spread_pct else ("same" if g.spread_pct == 0 else "")
        others = ", ".join(f"{labels.get(o.shop, o.shop)} EUR {o.price:,.0f}" for o in g.ranked[1:])
        return f"{star} {name:<37}{cheapest:<27}{spread:>6}  {others}"

    _print(f"  {'product':<37}{'cheapest':<27}{'spread':>6}  other shops")
    _print("  " + "-" * 94)
    for g in multi:
        _print(row(g))
    single = [g for g in groups if len(g.ranked) == 1]
    if single and args.min_shops > 1:
        _print(f"\nsold by one shop only ({len(single)}):")
        for g in sorted(single, key=lambda x: x.cheapest.price):
            _print(row(g))
    _print("\n* identified by the watchlist matcher; the rest are grouped by model code, which is a heuristic.")
    return 0


def cmd_check_shops(args) -> int:
    """Fetch each shop's monitor listing and report what came back.

    The six category URLs are the one part of this bot that cannot be verified away from a machine that
    can actually reach the shops, so this is the command to run first on the laptop. A shop that reports
    0 items, or an error naming shops_config, needs its category pinned in config.json.
    """
    from monbot.fetch import Fetcher
    from monbot.shops import SHOPS
    cfg = config_mod.load()
    fetch_cfg = cfg.get("fetch", {})
    fetcher = Fetcher(timeout=float(fetch_cfg.get("timeout_s", 40)), pause=float(fetch_cfg.get("pause_s", 1.0)),
                      playwright_mode=fetch_cfg.get("playwright", "auto"))
    crit = criteria_mod.from_config(cfg)
    wl = watchlist_mod.load()
    models = wl.watched(crit)
    bad = 0
    try:
        for name, cls in SHOPS.items():
            if args.shop and name not in args.shop:
                continue
            shop = cls(fetcher)
            try:
                items = shop.fetch_items(models)
                n_candidates = sum(1 for it in items if looks_like_candidate(it.title, crit))
                flag = "ok " if items else "ERR"
                if not items:
                    bad += 1
                _print(f"  {flag} {name:<12} {len(items):>4} items, {n_candidates:>3} fit {crit.label}")
                for it in items[:3]:
                    _print(f"       e.g. EUR {(it.price or 0):>8,.2f}  {it.title[:80]}")
            except Exception as e:
                bad += 1
                _print(f"  ERR {name:<12} {type(e).__name__}: {e}")
    finally:
        fetcher.close()
    _print("\nall six shops answered" if not bad else f"\n{bad} shop(s) need attention; see shops_config in config.json")
    return 1 if bad else 0


def cmd_test_notify(args) -> int:
    from monbot import notify
    cfg = config_mod.load()
    sent = notify.send(cfg, "Monitor Deal Bot test", "Notifications are working. Topic: " + cfg["notify"]["ntfy"]["topic"],
                       url="http://%s:%d/" % (cfg["ui"]["host"], int(cfg["ui"]["port"])))
    _print("sent via:", ", ".join(sent) or "nothing (check config)")
    return 0 if sent else 1


def cmd_validate(args) -> int:
    wl = watchlist_mod.load()
    crit = criteria_mod.active()
    problems = wl.validate(crit)
    _print(f"criteria: {crit.size_label} {crit.panel_label}, {crit.spec_label}")
    _print(f"{len(wl.models)} models ({len(wl.watched(crit))} watched), {len(wl.rejected)} rejected")
    for p in problems:
        _print("  !", p)
    return 1 if problems else 0


def cmd_serve(args) -> int:
    from monbot.scheduler import Scheduler
    from monbot.web.app import create_app
    cfg = config_mod.load()
    store = Store()
    sched = Scheduler(store)
    sched.start()
    app = create_app(store, sched)
    host, port = cfg["ui"]["host"], int(cfg["ui"]["port"])
    _print(f"Monitor Deal Bot dashboard: http://{host}:{port}")
    if args.open:
        webbrowser.open(f"http://{host}:{port}")
    try:
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
    finally:
        sched.stop()
    return 0


def cmd_task(args, action: str) -> int:
    from monbot import tasksched
    fn = {"install": tasksched.install, "uninstall": tasksched.uninstall,
          "status": tasksched.query, "run": tasksched.run_task, "restart": tasksched.restart_task}[action]
    _print(fn())
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="monbot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run-once", help="run one price check now")
    s.add_argument("--dry-run", action="store_true", help="evaluate rules but send nothing")
    s.add_argument("--shop", action="append", choices=list(SHOPS), help="limit to these shops")
    s.set_defaults(fn=cmd_run_once)

    s = sub.add_parser("report", help="print current prices per model and shop")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("discover", help="list titles in the shops that fit the criteria but are not on the watchlist")
    s.add_argument("--shop", action="append", choices=list(SHOPS))
    s.set_defaults(fn=cmd_discover)

    s = sub.add_parser("check-shops", help="confirm each shop's monitor category is reachable and parses")
    s.add_argument("--shop", action="append", choices=list(SHOPS))
    s.set_defaults(fn=cmd_check_shops)

    s = sub.add_parser("compare", help="cross-shop price comparison for every monitor at this size")
    s.add_argument("--min-shops", type=int, default=2, help="only show products sold by at least N shops")
    s.set_defaults(fn=cmd_compare)

    s = sub.add_parser("test-notify", help="send a test toast and ntfy push")
    s.set_defaults(fn=cmd_test_notify)

    s = sub.add_parser("validate", help="validate watchlist.json")
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
