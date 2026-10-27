"""Local dashboard (Flask). Bound to 127.0.0.1 by `main.py serve`."""
from __future__ import annotations
import logging
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from .. import config as config_mod
from .. import criteria as criteria_mod
from .. import notify
from .. import watchlist as watchlist_mod
from ..criteria import CONNECTIONS, HEIGHT_TYPES
from ..engine import discover, due_shops, enabled_shops, shop_labels
from ..models import Specs
from ..scheduler import Scheduler
from ..scoring import rank_models, score_model
from ..shops import COUNTRIES, SHOPS, shop_country
from ..store import Store
from ..watchlist import Model, Rejected

log = logging.getLogger("soundbot.web")
HERE = Path(__file__).resolve().parent


class DiscoverState:
    def __init__(self, store: Store):
        self.store = store
        self.running = False
        self.result: dict[str, list] = {}
        self.ran_at: str = ""
        self.error = ""
        self.progress = ""
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        try:
            res = discover(progress=lambda m: setattr(self, "progress", m), store=self.store)
            self.result = {shop: [it.__dict__ for it in items] for shop, items in res.items()}
            self.error = ""
        except Exception as e:
            log.exception("discover failed")
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.ran_at = datetime.now().isoformat(timespec="seconds")
            self.running = False
            self.progress = ""


def _fmt_price(p):
    return "" if p is None else f"€{p:,.2f}"


def _fmt_dt(s):
    if not s:
        return ""
    try:
        return datetime.fromisoformat(s).strftime("%d %b %H:%M")
    except Exception:
        return s


def _conn(value: str, what: str) -> str:
    """'wireless_included' -> 'wireless sub in the box'."""
    text = {"wireless_included": "wireless {w} in the box",
            "wireless_optional": "wireless {w} available",
            "built_in": "{w} built into the bar",
            "wired": "WIRED {w}",
            "none": "no {w}"}.get(value, "{w} unknown")
    return text.format(w=what)


def create_app(store: Store, sched: Scheduler) -> Flask:
    app = Flask(__name__, template_folder=str(HERE / "templates"), static_folder=str(HERE / "static"))
    app.config["JSON_AS_ASCII"] = False
    disc = DiscoverState(store)
    labels = shop_labels()

    app.jinja_env.filters["price"] = _fmt_price
    app.jinja_env.filters["dt"] = _fmt_dt
    app.jinja_env.globals.update(labels=labels, countries=COUNTRIES, connections=CONNECTIONS,
                                 height_types=HEIGHT_TYPES, conn=_conn, country_of=shop_country)

    def current_grid():
        cfg = config_mod.load()
        wl = watchlist_mod.load()
        shops = enabled_shops(cfg)
        rows = store.current_offers()
        cell: dict[tuple[str, str], dict] = {}
        for r in rows:
            key = (r["model_key"], r["shop"])
            d = dict(r)
            if key not in cell or (d["price"] or 1e9) < (cell[key]["price"] or 1e9):
                cell[key] = d
        best_prices: dict[str, float] = {}
        rows_by_model: dict[str, dict] = {}
        for m in wl.models:
            cells = {s: cell.get((m.model_key, s)) for s in shops}
            priced = [c for c in cells.values() if c and c["price"] and c["in_stock"] != 0]
            best = min(priced, key=lambda c: c["price"]) if priced else None
            if best:
                best_prices[m.model_key] = best["price"]
            rows_by_model[m.model_key] = {"cells": cells, "best": best}
        grid = []
        for rank, m, sc in rank_models(wl.models, cfg, best_prices):
            low = store.lowest_ever(m.model_key)
            grid.append({"model": m, "rank": rank, "score": sc, **rows_by_model[m.model_key],
                         "lowest": dict(low) if low else None})
        by_country = [(c, [s for s in shops if shop_country(s) == c]) for c in COUNTRIES]
        by_country = [(c, ss) for c, ss in by_country if ss]
        return cfg, wl, shops, grid, by_country

    # ---------------- pages ----------------
    @app.get("/")
    def dashboard():
        cfg, wl, shops, grid, by_country = current_grid()
        runs = store.last_runs(1)
        last_run = dict(runs[0]) if runs else None
        shop_runs = [dict(r) for r in store.shop_runs(last_run["id"])] if last_run else []
        _due, held = due_shops(store, cfg, enabled_shops(cfg))
        return render_template("dashboard.html", cfg=cfg, shops=shops, grid=grid, by_country=by_country,
                               status=sched.status(), last_run=last_run, shop_runs=shop_runs, held=held)

    @app.get("/model/<path:model_key>")
    def model_page(model_key):
        wl = watchlist_mod.load()
        m = wl.get(model_key)
        if m is None:
            abort(404)
        hist = [dict(r) for r in store.history(model_key, days=365)]
        series: dict[str, list] = {}
        for h in hist:
            if h["price"] is None:
                continue
            series.setdefault(h["shop"], []).append({"x": h["seen_at"], "y": h["price"]})
        current = [dict(r) for r in store.current_offers() if r["model_key"].upper() == model_key.upper()]
        alerts = [dict(r) for r in store.alerts(limit=50, model_key=model_key)]
        cfg, _wl, _shops, grid, _bc = current_grid()
        row = next((g for g in grid if g["model"].model_key == m.model_key), None)
        return render_template("model.html", m=m, series=series, current=current, alerts=alerts,
                               lowest=dict(store.lowest_ever(model_key) or {}) or None,
                               rank=row["rank"] if row else None, score=row["score"] if row else score_model(m, cfg),
                               total=len(grid))

    @app.get("/ranking")
    def ranking_page():
        cfg, wl, shops, grid, _bc = current_grid()
        return render_template("ranking.html", cfg=cfg, grid=grid)

    @app.get("/alerts")
    def alerts_page():
        return render_template("alerts.html", alerts=[dict(r) for r in store.alerts(limit=300)])

    @app.get("/watchlist")
    def watchlist_page():
        wl = watchlist_mod.load()
        edit_key = request.args.get("edit")
        edit = wl.get(edit_key) if edit_key else None
        prefill = {k: request.args.get(k, "") for k in ("brand", "model_key", "aliases", "notes")}
        crit = criteria_mod.active()
        return render_template("watchlist.html", wl=wl, edit=edit, prefill=prefill, crit=crit,
                               problems=wl.validate(crit))

    @app.post("/watchlist/save")
    def watchlist_save():
        wl = watchlist_mod.load()
        f = request.form
        key = (f.get("model_key") or "").strip()
        if not key:
            abort(400, "model_key required")
        original = (f.get("original_key") or "").strip()

        def _num(v, cast=int):
            try:
                return cast(v) if str(v).strip() else None
            except (TypeError, ValueError):
                return None

        def _choice(name, allowed):
            v = (f.get(name) or "").strip()
            return v if v in allowed else ""

        m = Model(
            brand=(f.get("brand") or "").strip(), model_key=key, family=(f.get("family") or "").strip(),
            year=_num(f.get("year")),
            specs=Specs(channels=_num(f.get("channels"), float), sub_channels=_num(f.get("sub_channels")),
                        height_channels=_num(f.get("height_channels")),
                        height_type=_choice("height_type", HEIGHT_TYPES),
                        subwoofer=_choice("subwoofer", CONNECTIONS), rears=_choice("rears", CONNECTIONS),
                        atmos=f.get("atmos") == "on", dtsx=f.get("dtsx") == "on",
                        earc=f.get("earc") == "on", hdmi_in=_num(f.get("hdmi_in"))),
            source_url=(f.get("source_url") or "").strip(),
            aliases=[a.strip() for a in (f.get("aliases") or "").split(",") if a.strip()],
            priority=f.get("priority") == "on", notes=(f.get("notes") or "").strip(),
            enabled=f.get("enabled", "on") == "on",
        )
        existing = wl.get(original or key)
        if existing is not None:
            m.review = existing.review          # review evidence is not edited here; keep it
        wl.models = [x for x in wl.models if x.model_key.upper() not in {key.upper(), original.upper()}]
        wl.models.append(m)
        watchlist_mod.save(wl)
        return redirect(url_for("watchlist_page"))

    @app.post("/watchlist/delete/<path:model_key>")
    def watchlist_delete(model_key):
        wl = watchlist_mod.load()
        wl.models = [x for x in wl.models if x.model_key.upper() != model_key.upper()]
        watchlist_mod.save(wl)
        return redirect(url_for("watchlist_page"))

    @app.post("/watchlist/reject/<path:model_key>")
    def watchlist_reject(model_key):
        wl = watchlist_mod.load()
        m = wl.get(model_key)
        if m:
            wl.models = [x for x in wl.models if x.model_key.upper() != model_key.upper()]
            wl.rejected.append(Rejected(brand=m.brand, model_key=m.model_key,
                                        reason=request.form.get("reason") or "rejected from UI",
                                        source_url=m.source_url, aliases=m.aliases))
            watchlist_mod.save(wl)
        return redirect(url_for("watchlist_page"))

    @app.post("/watchlist/unreject/<path:model_key>")
    def watchlist_unreject(model_key):
        wl = watchlist_mod.load()
        wl.rejected = [r for r in wl.rejected if r.model_key.upper() != model_key.upper()]
        watchlist_mod.save(wl)
        return redirect(url_for("watchlist_page", edit=model_key))

    @app.get("/settings")
    def settings_page():
        cfg = config_mod.load()
        return render_template("settings.html", cfg=cfg, shops=list(SHOPS),
                               crit=criteria_mod.from_config(cfg), shop_country=shop_country,
                               saved=request.args.get("saved"))

    @app.post("/settings")
    def settings_save():
        cfg = config_mod.load()
        f = request.form

        def _num(name, default, cast=float):
            try:
                return cast(f.get(name, default))
            except (TypeError, ValueError):
                return default

        cfg["rules"]["cross_shop_pct"] = _num("cross_shop_pct", cfg["rules"]["cross_shop_pct"])
        cfg["rules"]["list_discount_pct"] = _num("list_discount_pct", cfg["rules"]["list_discount_pct"])
        cfg["rules"]["dedupe_days"] = _num("dedupe_days", cfg["rules"]["dedupe_days"], int)
        cfg["rules"]["back_in_stock"] = f.get("back_in_stock") == "on"
        scope = (f.get("cross_shop_scope") or "").strip().lower()
        if scope in ("country", "all"):
            cfg["rules"]["cross_shop_scope"] = scope
        cfg["schedule"]["interval_hours"] = _num("interval_hours", cfg["schedule"]["interval_hours"])
        cfg["notify"]["toast"] = f.get("toast") == "on"
        cfg["notify"]["ntfy"]["enabled"] = f.get("ntfy_enabled") == "on"
        cfg["notify"]["ntfy"]["topic"] = (f.get("ntfy_topic") or "").strip()
        cfg["notify"]["ntfy"]["server"] = (f.get("ntfy_server") or "https://ntfy.sh").strip()
        cfg["price_range"]["min"] = _num("price_min", cfg["price_range"]["min"])
        cfg["price_range"]["max"] = _num("price_max", cfg["price_range"]["max"])
        cfg.setdefault("scoring", {})
        cfg["scoring"]["fit_weight"] = _num("fit_weight", cfg["scoring"].get("fit_weight", 0.5))
        cfg["scoring"]["review_weight"] = _num("review_weight", cfg["scoring"].get("review_weight", 0.5))
        profile = (f.get("scoring_profile") or "").strip().lower()
        if profile in ("cinema", "music"):
            cfg["scoring"]["profile"] = profile

        crit = cfg.setdefault("criteria", {})
        crit["min_height_channels"] = _num("min_height_channels", crit.get("min_height_channels", 2), int)
        crit["min_channels"] = _num("min_channels", crit.get("min_channels", 3.0))
        crit["require_physical_height"] = f.get("require_physical_height") == "on"
        crit["require_earc"] = f.get("require_earc") == "on"
        crit["no_wired_speakers"] = f.get("no_wired_speakers") == "on"
        crit["require_sub_included"] = f.get("require_sub_included") == "on"
        crit["require_rears_included"] = f.get("require_rears_included") == "on"

        for code in COUNTRIES:
            cfg.setdefault("countries", {})[code] = f.get(f"country_{code}") == "on"
        for s in SHOPS:
            cfg["shops"][s] = f.get(f"shop_{s}") == "on"
        config_mod.save(cfg)
        sched.reschedule()
        return redirect(url_for("settings_page", saved=1))

    @app.get("/discover")
    def discover_page():
        return render_template("discover.html", disc=disc, crit=criteria_mod.active())

    # ---------------- JSON API ----------------
    @app.get("/api/status")
    def api_status():
        st = sched.status()
        st["discover"] = {"running": disc.running, "ran_at": disc.ran_at, "progress": disc.progress,
                          "error": disc.error}
        return jsonify(st)

    @app.post("/api/run")
    def api_run():
        ok = sched.run_now()
        return jsonify({"started": ok, "status": sched.status()})

    @app.post("/api/test-notify")
    def api_test_notify():
        cfg = config_mod.load()
        sent = notify.send(cfg, "Soundbar Deal Bot test", "Notifications are working.",
                           url="http://127.0.0.1:%d/" % int(cfg["ui"]["port"]))
        return jsonify({"sent": sent})

    @app.post("/api/discover")
    def api_discover():
        return jsonify({"started": disc.start()})

    @app.get("/api/offers")
    def api_offers():
        mk = request.args.get("model")
        rows = [dict(r) for r in store.current_offers()]
        if mk:
            rows = [r for r in rows if r["model_key"].upper() == mk.upper()]
        for r in rows:
            r["country"] = shop_country(r["shop"])
        return jsonify(rows)

    @app.get("/api/history")
    def api_history():
        mk = request.args.get("model") or ""
        return jsonify([dict(r) for r in store.history(mk, days=int(request.args.get("days", 365)))])

    @app.get("/api/watchlist")
    def api_watchlist_get():
        wl = watchlist_mod.load()
        return jsonify({"models": [m.to_dict() for m in wl.models], "rejected": [r.__dict__ for r in wl.rejected]})

    @app.put("/api/watchlist")
    def api_watchlist_put():
        data = request.get_json(force=True)
        wl = watchlist_mod.Watchlist(models=[watchlist_mod.model_from_dict(d) for d in data.get("models", [])],
                                     rejected=[Rejected(**r) for r in data.get("rejected", [])])
        watchlist_mod.save(wl)
        return jsonify({"ok": True, "problems": wl.validate(criteria_mod.active())})

    @app.get("/api/config")
    def api_config_get():
        return jsonify(config_mod.load())

    @app.put("/api/config")
    def api_config_put():
        cfg = config_mod.load()
        cfg = config_mod._merge(cfg, request.get_json(force=True))
        config_mod.save(cfg)
        sched.reschedule()
        return jsonify(cfg)

    return app
