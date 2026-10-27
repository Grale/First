"""Offline checks: no network, no shop, no surprises.

    python tools/selftest.py

1. Replays the real shop titles in tools/fixtures/shop_titles.json through the matcher and reports any
   listing that stopped resolving to the model it resolved to when the fixture was captured. This is
   what catches a watchlist edit that makes "Bar 1300" swallow "Bar 1300MK2", or an alias that lets the
   rejected Bar 800MK2 be read as the Bar 800.
2. Validates watchlist.json against the active criteria.
3. Checks the price parser on the formats the shops actually print.
4. Checks that the Skroutz adapter refuses the paths Skroutz's robots.txt disallows.
5. Runs the Skroutz card parser and the Public token reader over small made-up pages, because those two
   shops turn away anything but a browser and cannot be exercised from a test.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soundbot import criteria as criteria_mod          # noqa: E402
from soundbot import watchlist as watchlist_mod        # noqa: E402
from soundbot.match import best_match, matches_rejected  # noqa: E402
from soundbot.shops.base import parse_price            # noqa: E402
from soundbot.shops.skroutz import Skroutz             # noqa: E402

FIXTURE = ROOT / "tools" / "fixtures" / "shop_titles.json"


def classify(title: str, models, wl, crit) -> str:
    m = best_match(title, models, crit, wl.rejected)
    if m:
        return m.model_key
    if matches_rejected(title, wl.rejected, crit):
        return "rejected"
    if crit.looks_like_candidate(title):
        return "candidate"
    return "ignore"


def check_titles(failures: list[str]) -> None:
    if not FIXTURE.exists():
        print("  ! no fixture file; skipped")
        return
    crit = criteria_mod.active()
    wl = watchlist_mod.load()
    models = wl.watched(crit)
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    total = changed = new_candidates = 0
    for shop, rows in data["shops"].items():
        for row in rows:
            total += 1
            got = classify(row["title"], models, wl, crit)
            if got == row["expected"]:
                continue
            if row["expected"] == "candidate" and got not in ("candidate", "ignore"):
                new_candidates += 1          # a candidate that is now researched and watched: progress
                continue
            changed += 1
            failures.append(f"{shop}: '{row['title'][:70]}' was {row['expected']}, now {got}")
    print(f"  {total} recorded titles, {changed} changed classification, "
          f"{new_candidates} former candidates now watched")


def check_watchlist(failures: list[str]) -> None:
    crit = criteria_mod.active()
    wl = watchlist_mod.load()
    problems = wl.validate(crit)
    print(f"  {len(wl.models)} models ({len(wl.watched(crit))} watched), {len(wl.rejected)} rejected")
    failures.extend(f"watchlist: {p}" for p in problems)


def check_prices(failures: list[str]) -> None:
    cases = [("€1,199.00", 1199.0), ("1.199,00 €", 1199.0), ("697 ,99€", 697.99), ("€85", 85.0),
             ("1,449.00", 1449.0), ("698.99", 698.99), ("", None), ("Price on request", None)]
    for text, want in cases:
        got = parse_price(text)
        if got != want:
            failures.append(f"parse_price({text!r}) = {got!r}, expected {want!r}")
    print(f"  {len(cases)} price formats")


def check_robots(failures: list[str]) -> None:
    allowed = ["/c/907/soundbars.html", "/search?keyphrase=HW-Q990H", "/s/12345/Samsung-HW-Q990H.html"]
    refused = ["/api/v3/skus", "/apiv2/categories", "/products/show?id=1", "/s/12345/shops_list",
               "/s/12345/price_graph", "/c/907/soundbars.html?filter_id=99"]
    for path in allowed:
        try:
            Skroutz._assert_allowed("https://www.skroutz.gr" + path)
        except ValueError as e:
            failures.append(f"skroutz refused an allowed path {path}: {e}")
    for path in refused:
        try:
            Skroutz._assert_allowed("https://www.skroutz.gr" + path)
            failures.append(f"skroutz allowed a disallowed path: {path}")
        except ValueError:
            pass
    print(f"  {len(allowed)} allowed and {len(refused)} disallowed Skroutz paths")


SKROUTZ_PAGE = """
<ul class="sku-list">
  <li class="cf card" data-skuid="41234567">
    <a href="/s/41234567/Samsung-HW-Q990H.html" title="Samsung HW-Q990H">Samsung HW-Q990H</a>
    <div class="price"><a href="/s/41234567/Samsung-HW-Q990H.html"><strong>1.389,00 &euro;</strong></a></div>
    <p class="shop-count">σε 24 καταστήματα</p>
  </li>
  <li class="cf card" data-skuid="39876543">
    <a href="/s/39876543/Sony-HT-A9000.html"><img alt="Sony HT-A9000 Bravia Theatre Bar 9"></a>
    <div class="price">776,00 &euro;</div>
  </li>
</ul>
"""
PUBLIC_PAGE = """
<html><body><script>
window.__CFG = {"token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7IndlYnNpdGVJZCI6OTksImRvbWFpbiI6InB1YmxpYy5nciIsInNjb3BlcyI6WyJzZWFyY2giXSwibmFtZSI6IkZyb250ZW5kIn19.c2lnbmF0dXJlLXBsYWNlaG9sZGVy"};
</script></body></html>
"""


def check_offline_parsers(failures: list[str]) -> None:
    from soundbot.fetch import Fetcher
    from soundbot.shops.public_like import PublicGr, _JWT_RE, _payload

    f = Fetcher()
    try:
        items = Skroutz(f)._cards(SKROUTZ_PAGE)
    finally:
        f.close()
    by_sku = {i.shop_sku: i for i in items}
    if set(by_sku) != {"41234567", "39876543"}:
        failures.append(f"skroutz parser found {sorted(by_sku)}, expected both SKUs")
    else:
        first = by_sku["41234567"]
        if first.price != 1389.0:
            failures.append(f"skroutz parser read price {first.price}, expected 1389.0")
        if "Q990H" not in first.title.upper():
            failures.append(f"skroutz parser read title {first.title!r}")
        if by_sku["39876543"].price != 776.0:
            failures.append(f"skroutz parser read price {by_sku['39876543'].price}, expected 776.0")
        if "HT-A9000" not in by_sku["39876543"].title.upper():
            failures.append("skroutz parser did not fall back to the image alt text for the title")

    # The category-first flow, and the empty page that ends a listing rather than failing it.
    class StubFetcher:
        timeout = 10
        pause = 1.0
        tier_used: dict = {}

        def __init__(self):
            self.asked: list[str] = []

        def _throttle(self):
            pass

        def close(self):
            pass

        def get(self, url, start_tier=1, wait_selector=None):
            self.asked.append(url)
            if "/c/" in url:
                return SKROUTZ_PAGE if "page=" not in url else "<ul></ul>"
            return "<ul></ul>"          # a search that finds nothing

    from soundbot import criteria as crit_mod
    from soundbot import watchlist as wl_mod
    crit = crit_mod.active()
    wl = wl_mod.load()
    some = [m for m in wl.watched(crit) if m.model_key in ("HW-Q990H", "HT-A9000")]
    stub = StubFetcher()
    got = Skroutz(stub).fetch_items(some)
    if not stub.asked or "/c/" not in stub.asked[0]:
        failures.append("skroutz asked for a search before the category listing")
    if len(got) != 2:
        failures.append(f"skroutz category flow returned {len(got)} items, expected 2")

    hits = [b for b in _JWT_RE.findall(PUBLIC_PAGE)
            if (_payload(b).get("data") or {}).get("domain") == PublicGr.domain
            and "search" in ((_payload(b).get("data") or {}).get("scopes") or [])]
    if len(hits) != 1:
        failures.append(f"public token reader found {len(hits)} tokens in a page with one")
    print(f"  {len(items)} Skroutz cards parsed, category-first flow in {len(stub.asked)} "
          f"requests, {len(hits)} Public token found")


def main() -> int:
    failures: list[str] = []
    for name, fn in (("shop titles", check_titles), ("watchlist", check_watchlist),
                     ("price parsing", check_prices), ("skroutz robots rules", check_robots),
                     ("offline parsers", check_offline_parsers)):
        print(f"{name}:")
        fn(failures)
    if failures:
        print(f"\n{len(failures)} problem(s):")
        for f in failures:
            print("  !", f)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
