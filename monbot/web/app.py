"""Local dashboard (Flask). Bound to 127.0.0.1 by `main.py serve`."""
from __future__ import annotations
import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for, abort

from .. import config as config_mod
from .. import criteria as criteria_mod
from .. import watchlist as watchlist_mod
from .. import notify
from ..criteria import PANEL_FAMILIES
from ..engine import discover, shop_labels
from ..scheduler import Scheduler
from ..scoring import PROFILES, rank_models, score_model
from ..shops import SHOPS
from ..store import Store
from ..watchlist import Model, Specs, Rejected

log = logging.getLogger("monbot.web")
HERE = Path(__file__).resolve().parent


class DiscoverState:
    def __init__(self):
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
            res = discover(progress=lambda m: setattr(self, "progress", m))
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


def create_app(store: Store, sched: Scheduler) -> Flask:
    app = Flask(__name__, template_folder=str(HERE / "templates"), static_folder=str(HERE / "static"))
    app.config["JSON_AS_ASCII"] = False
    disc = DiscoverState()
    labels = shop_labels()

    app.jinja_env.filters["price"] = _fmt_price
    app.jinja_env.filters["dt"] = _fmt_dt
    app.jinja_env.globals["labels"] = labels

    def current_grid():
        cfg = config_mod.load()
        wl = watchlist_mod.load()
        shops = [n for n in SHOPS if cfg.get("shops", {}).get(n, True)]
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
        return cfg, wl, shops, grid

    # ---------------- pages ----------------
    @app.get("/")
    def dashboard():
        cfg, wl, shops, grid = current_grid()
        runs = store.last_runs(1)
        last_run = dict(runs[0]) if runs else None
        shop_runs = [dict(r) for r in store.shop_runs(last_run["id"])] if last_run else []
        return render_template("dashboard.html", cfg=cfg, shops=shops, grid=grid, status=sched.status(),
                               last_run=last_run, shop_runs=shop_runs)

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
        cfg, wl2, shops, grid = current_grid()
        row = next((g for g in grid if g["model"].model_key == m.model_key), None)
        return render_template("model.html", m=m, series=series, current=current, alerts=alerts,
                               lowest=dict(store.lowest_ever(model_key) or {}) or None,
                               rank=row["rank"] if row else None, score=row["score"] if row else score_model(m, cfg),
                               total=len(grid))

    @app.get("/ranking")
    def ranking_page():
        cfg, wl, shops, grid = current_grid()
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
        return render_template("watchlist.html", wl=wl, edit=edit, prefill=prefill,
                               problems=wl.validate(criteria_mod.active()))

    @app.post("/watchlist/save")
    def watchlist_save():
        wl = watchlist_mod.load()
        f = request.form
        key = (f.get("model_key") or "").strip()
        if not key:
            abort(400, "model_key required")
        original = (f.get("original_key") or "").strip()

        def _int(v):
            # v is None when the field is absent from the POST, and "" when it was left blank. Both
            # mean "not given"; str(None) is "None", which is truthy, so the None case must come first.
            if v is None or not str(v).strip():
                return None
            try:
                return int(v)
            except ValueError:
                return None

        def _float(v):
            if v is None or not str(v).strip():
                return None
            try:
                return float(v)
            except ValueError:
                return None

        def _tri(v):
            """A select with an "unverified" option, so editing a model cannot silently turn an
            unknown fact into a "no". A checkbox cannot express the difference and this field is
            used both to qualify a model and to score it."""
            v = (v or "").strip()
            return None if v == "" else v == "1"

        existing = wl.get(original or key)
        m = Model(
            brand=(f.get("brand") or "").strip(), model_key=key, family=(f.get("family") or "").strip(),
            year=_int(f.get("year")), panel=(f.get("panel") or "").strip(),
            size_inch=_float(f.get("size_inch")),
            specs=Specs(
                hz=_int(f.get("hz")), width=_int(f.get("width")), height=_int(f.get("height")),
                response_ms=_float(f.get("response_ms")), usb_c_pd_w=_int(f.get("usb_c_pd_w")),
                kvm=_tri(f.get("kvm")), height_adjust=_tri(f.get("height_adjust")),
                curvature=(f.get("curvature") or "").strip(),
                dp_version=(f.get("dp_version") or "").strip(), hdr=(f.get("hdr") or "").strip(),
                srgb_pct=_int(f.get("srgb_pct")), dci_p3_pct=_int(f.get("dci_p3_pct")),
                contrast=_int(f.get("contrast")),
                tuv_eye_comfort_stars=_int(f.get("tuv_eye_comfort_stars")),
                vrr=_tri(f.get("vrr")), vrr_brand=(f.get("vrr_brand") or "").strip(),
                burn_in_warranty_years=_int(f.get("burn_in_warranty_years")),
            ),
            source_url=(f.get("source_url") or "").strip(),
            aliases=[a.strip() for a in (f.get("aliases") or "").split(",") if a.strip()],
            priority=f.get("priority") == "on", notes=(f.get("notes") or "").strip(),
            enabled=f.get("enabled", "on") == "on",
            # the form does not edit review evidence; keep what the builder put there
            review=dict(existing.review) if existing else {},
        )
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
        return render_template("settings.html", cfg=cfg, shops=list(SHOPS), crit=criteria_mod.from_config(cfg),
                               panel_families=PANEL_FAMILIES, saved=request.args.get("saved"))

    @app.post("/settings")
    def settings_save():
        cfg = config_mod.load()
        f = request.form

        def _num(name, default, cast=float):
            try:
                return cast(f.get(name, default))
            except (TypeError, ValueError):
                return default

        # An empty POST must not be read as "every checkbox was unticked": that would disable all six
        # shops and clear every requirement at once. Only a POST that carries the form's own marker is
        # allowed to turn a checkbox off.
        full_form = bool(f.get("settings_form"))

        def _check(name, current):
            return (f.get(name) == "on") if full_form else bool(current)

        cfg["rules"]["cross_shop_pct"] = _num("cross_shop_pct", cfg["rules"]["cross_shop_pct"])
        cfg["rules"]["list_discount_pct"] = _num("list_discount_pct", cfg["rules"]["list_discount_pct"])
        cfg["rules"]["dedupe_days"] = _num("dedupe_days", cfg["rules"]["dedupe_days"], int)
        cfg["rules"]["back_in_stock"] = _check("back_in_stock", cfg["rules"]["back_in_stock"])
        cfg["schedule"]["interval_hours"] = _num("interval_hours", cfg["schedule"]["interval_hours"])
        cfg["notify"]["toast"] = _check("toast", cfg["notify"]["toast"])
        cfg["notify"]["ntfy"]["enabled"] = _check("ntfy_enabled", cfg["notify"]["ntfy"]["enabled"])
        if f.get("ntfy_topic") is not None or full_form:
            cfg["notify"]["ntfy"]["topic"] = (f.get("ntfy_topic") or "").strip() or cfg["notify"]["ntfy"]["topic"]
        cfg["notify"]["ntfy"]["server"] = (f.get("ntfy_server") or cfg["notify"]["ntfy"]["server"] or "https://ntfy.sh").strip()
        cfg["price_range"]["min"] = _num("price_min", cfg["price_range"]["min"])
        cfg["price_range"]["max"] = _num("price_max", cfg["price_range"]["max"])
        cfg.setdefault("scoring", {})
        cfg["scoring"]["fit_weight"] = _num("fit_weight", cfg["scoring"].get("fit_weight", 0.5))
        cfg["scoring"]["review_weight"] = _num("review_weight", cfg["scoring"].get("review_weight", 0.5))
        profile = (f.get("scoring_profile") or "").strip().lower()
        if profile in PROFILES:
            cfg["scoring"]["profile"] = profile

        crit = cfg.setdefault("criteria", {})
        sizes = [int(t) for t in re.findall(r"\d+", f.get("sizes") or "") if 10 <= int(t) <= 60]
        if sizes:
            crit["sizes"] = sorted(set(sizes))
        panels = [k for k in PANEL_FAMILIES if f.get(f"panel_{k}") == "on"]
        if panels:
            crit["panels"] = ["any"] if "any" in panels else panels
        crit["min_hz"] = _num("min_hz", crit.get("min_hz", 100), int)
        crit["min_width"] = _num("min_width", crit.get("min_width", 3440), int)
        crit["min_height"] = _num("min_height", crit.get("min_height", 1440), int)
        crit["require_usb_c_pd_w"] = _num("require_usb_c_pd_w", crit.get("require_usb_c_pd_w", 0), int)
        crit["require_height_adjust"] = _check("require_height_adjust", crit.get("require_height_adjust", True))
        crit["require_kvm"] = _check("require_kvm", crit.get("require_kvm", False))
        crit["require_vrr"] = _check("require_vrr", crit.get("require_vrr", False))
        for shop_name in SHOPS:
            cfg["shops"][shop_name] = _check(f"shop_{shop_name}", cfg["shops"].get(shop_name, True))
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
        st["discover"] = {"running": disc.running, "ran_at": disc.ran_at, "progress": disc.progress, "error": disc.error}
        return jsonify(st)

    @app.post("/api/run")
    def api_run():
        ok = sched.run_now()
        return jsonify({"started": ok, "status": sched.status()})

    @app.post("/api/test-notify")
    def api_test_notify():
        cfg = config_mod.load()
        sent = notify.send(cfg, "Monitor Deal Bot test", "Notifications are working.", url="http://127.0.0.1:%d/" % int(cfg["ui"]["port"]))
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
