"""Dashboard test: every page answers 200, and the settings form round-trips without wiping itself.

    python tests/test_web.py

Runs against a throwaway copy of config.json and a throwaway SQLite file, so it never touches the real
config or price history. The empty-form case is the one that matters: an HTML checkbox sends nothing
when it is off, so a bare POST used to read as "untick everything" - which would have disabled all six
shops and cleared every requirement in one request.
"""
from __future__ import annotations
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from monbot import config as config_mod          # noqa: E402
from monbot import watchlist as watchlist_mod    # noqa: E402
from monbot.scheduler import Scheduler           # noqa: E402
from monbot.store import Store                   # noqa: E402
from monbot.web.app import create_app            # noqa: E402

failures: list[str] = []
checks = 0


def check(cond: bool, what: str) -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(what)


FULL_FORM = {
    "settings_form": "1",
    "sizes": "34", "min_hz": "120", "min_width": "3440", "min_height": "1440",
    "panel_oled": "on", "panel_miniled": "on", "panel_ips": "on",
    "require_height_adjust": "on", "require_usb_c_pd_w": "65", "require_kvm": "on",
    "cross_shop_pct": "12", "list_discount_pct": "25", "dedupe_days": "5", "back_in_stock": "on",
    "price_min": "250", "price_max": "1800",
    "scoring_profile": "work", "fit_weight": "0.6", "review_weight": "0.4",
    "interval_hours": "3",
    "toast": "on", "ntfy_enabled": "on", "ntfy_topic": "monitor-deals-cy-34-test",
    "ntfy_server": "https://ntfy.sh",
    "shop_electroline": "on", "shop_scandia": "on", "shop_megaelectric": "on",
    "shop_stephanis": "on", "shop_public": "on", "shop_kotsovolos": "on",
}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="monbot-test-"))
    shutil.copy(ROOT / "config.json", tmp / "config.json")
    shutil.copy(ROOT / "watchlist.json", tmp / "watchlist.json")
    # Point both files at the throwaway copies: the watchlist form test below saves a model, and it
    # must not rewrite the committed watchlist.json.
    config_mod.CONFIG_PATH = tmp / "config.json"
    watchlist_mod.WATCHLIST_PATH = tmp / "watchlist.json"

    store = Store(tmp / "prices.db")
    sched = Scheduler(store)                          # deliberately not started
    app = create_app(store, sched)
    app.config.update(TESTING=True)
    client = app.test_client()

    wl = watchlist_mod.load()
    a_key = wl.models[0].model_key if wl.models else "U3425WE"

    # ---- every page answers ----
    for path in ("/", "/ranking", "/watchlist", "/settings", "/discover", "/alerts",
                 f"/model/{a_key}"):
        r = client.get(path)
        check(r.status_code == 200, f"GET {path} returned {r.status_code}, expected 200")

    r = client.get("/model/does-not-exist")
    check(r.status_code == 404, f"GET an unknown model returned {r.status_code}, expected 404")

    for path in ("/api/status", "/api/config", "/api/watchlist", "/api/offers",
                 f"/api/history?model={a_key}"):
        r = client.get(path)
        check(r.status_code == 200, f"GET {path} returned {r.status_code}, expected 200")

    # ---- settings round-trip ----
    r = client.post("/settings", data=FULL_FORM)
    check(r.status_code in (302, 303), f"POST /settings returned {r.status_code}, expected a redirect")
    saved = json.loads((tmp / "config.json").read_text(encoding="utf-8"))
    crit = saved.get("criteria", {})
    check(crit.get("sizes") == [34], f"sizes did not save: {crit.get('sizes')}")
    check(sorted(crit.get("panels", [])) == ["ips", "miniled", "oled"],
          f"panels did not save: {crit.get('panels')}")
    check(crit.get("min_hz") == 120, f"min_hz did not save: {crit.get('min_hz')}")
    check(crit.get("min_width") == 3440 and crit.get("min_height") == 1440,
          f"resolution floor did not save: {crit.get('min_width')}x{crit.get('min_height')}")
    check(crit.get("require_usb_c_pd_w") == 65,
          f"require_usb_c_pd_w did not save: {crit.get('require_usb_c_pd_w')}")
    check(crit.get("require_height_adjust") is True, "require_height_adjust did not save")
    check(crit.get("require_kvm") is True, "require_kvm did not save")
    check(saved["scoring"]["profile"] == "work", "scoring profile did not save")
    check(saved["price_range"] == {"min": 250, "max": 1800}, "price range did not save")
    check(all(saved["shops"].values()), "shops were not all saved as enabled")

    # turning a requirement back off must work when the form really says so
    off = dict(FULL_FORM)
    off.pop("require_kvm")
    client.post("/settings", data=off)
    saved = json.loads((tmp / "config.json").read_text(encoding="utf-8"))
    check(saved["criteria"]["require_kvm"] is False,
          "unticking KVM on a real form submission did not take effect")

    # ---- an empty POST must not wipe anything ----
    before = json.loads((tmp / "config.json").read_text(encoding="utf-8"))
    r = client.post("/settings", data={})
    check(r.status_code in (302, 303), f"empty POST /settings returned {r.status_code}")
    after = json.loads((tmp / "config.json").read_text(encoding="utf-8"))
    check(after["criteria"] == before["criteria"],
          f"an empty form changed the criteria block:\n  before {before['criteria']}\n  after  {after['criteria']}")
    check(after["shops"] == before["shops"], "an empty form changed which shops are enabled")
    check(after["notify"]["ntfy"]["topic"] == before["notify"]["ntfy"]["topic"],
          "an empty form cleared the ntfy topic")
    check(after["price_range"] == before["price_range"], "an empty form changed the price range")

    # ---- the watchlist form keeps "unverified" distinct from "no" ----
    model = wl.get("LS34BG850")
    if model is not None:
        check(model.specs.kvm is None, "test fixture changed: LS34BG850 should have an unknown KVM")
        r = client.post("/watchlist/save", data={
            "model_key": "LS34BG850", "original_key": "LS34BG850", "brand": "Samsung",
            "panel": "QD-OLED", "size_inch": "34", "hz": "175", "width": "3440", "height": "1440",
            "kvm": "", "height_adjust": "1", "vrr": "1", "enabled": "on",
            "source_url": model.source_url, "aliases": ", ".join(model.aliases),
        })
        check(r.status_code in (302, 303), f"POST /watchlist/save returned {r.status_code}")
        again = watchlist_mod.load().get("LS34BG850")
        check(again is not None and again.specs.kvm is None,
              "an unverified KVM became a definite 'no' after a round-trip through the form")
        check(again is not None and again.specs.height_adjust is True,
              "height_adjust did not survive the form round-trip")
        check(again is not None and bool(again.review),
              "the form wiped the review evidence the builder attached")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{checks - len(failures)}/{checks} checks passed")
    for f in failures:
        print("  FAIL:", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
