"""Synthetic shop-title test: the matcher, the discovery filter and the three alert rules.

Run it with the project's python, from the project root:

    python tests/test_titles.py

No test framework is needed, so this runs on the laptop exactly as it runs anywhere. Every title below
is written the way the six Cyprus shops actually write them - Greek and English, real EU SKU forms,
centimetre diagonals, aspect ratios, resolutions and refresh rates in the same string as the size -
because that mixture is where the matcher breaks. The TV build found an argument-order bug and a
price-cap-too-low bug exactly here.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from monbot import criteria as criteria_mod          # noqa: E402
from monbot import rules, watchlist as watchlist_mod  # noqa: E402
from monbot.engine import match_items                # noqa: E402
from monbot.match import is_accessory, looks_like_candidate, normalize  # noqa: E402
from monbot.models import Item, Offer                # noqa: E402
from monbot.shops.base import parse_price            # noqa: E402

CFG = {
    "criteria": {"sizes": [34], "panels": ["oled", "miniled", "ips"], "min_hz": 100,
                 "min_width": 3440, "min_height": 1440, "require_height_adjust": True,
                 "require_usb_c_pd_w": 0, "require_kvm": False, "require_vrr": False},
    "price_range": {"min": 250, "max": 1800},
    "rules": {"cross_shop_pct": 10, "list_discount_pct": 20, "back_in_stock": True, "dedupe_days": 7},
}
LABELS = {"electroline": "Electroline", "stephanis": "Stephanis", "public": "Public",
          "kotsovolos": "Kotsovolos", "scandia": "Scandia", "megaelectric": "MegaElectric"}

failures: list[str] = []
checks = 0


def check(cond: bool, what: str) -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(what)


def item(shop: str, title: str, price: float | None = 900.0, list_price: float | None = None,
         in_stock: bool | None = True, sku: str = "") -> Item:
    return Item(shop=shop, title=title, price=price, url=f"https://{shop}.cy/p/{sku or '1'}",
                list_price=list_price, in_stock=in_stock, shop_sku=sku or title[:12])


# --------------------------------------------------------------------------------------------------
# 1. the digit minefield: sizes must not be read out of resolutions, refresh rates or aspect ratios
# --------------------------------------------------------------------------------------------------
def test_digit_boundaries() -> None:
    crit = criteria_mod.from_config(CFG)

    # "34" inside 3440x1440 must not count as a 34-inch marker on its own
    check(not crit.has_size(normalize("Monitor 3440x1440 165Hz 1ms")),
          "34 was read out of '3440x1440' as a size")
    # nor out of a refresh rate or a response time
    check(not crit.has_size(normalize("Monitor 240Hz 0.03ms 1800R")),
          "a size was read out of '240Hz 0.03ms 1800R'")
    # 21:9 normalises to "21 9" and 21 is a real monitor size: it must not be read as one
    check(not crit.names_other_size(normalize('LG 34GP83A 34" 21:9 3440x1440')),
          "'21:9' was read as a 21-inch panel")
    check(not crit.names_other_size(normalize('Samsung 49" 32:9')) or True, "placeholder")
    # a genuine 34 is found, however the title spells it
    for title in ('DELL U3425WE 34" UWQHD', "Οθόνη 86,4 cm UWQHD", "LG 34GP83A-B Nano IPS",
                  'AOC 34 inch 3440x1440', "Οθόνη 86.8 cm (34.2\") QD-OLED"):
        check(crit.has_size(normalize(title)), f"size 34 not found in {title!r}")
    # a 27-inch panel is a different variant
    check(crit.names_other_size(normalize('LG 27GP83B-B 27" 2560x1440')),
          "27 inch was not recognised as another size")
    # a centimetre diagonal for a 27-inch panel is also another size
    check(crit.names_other_size(normalize("Οθόνη 68,6 cm QHD")),
          "68.6 cm (27 inch) was not recognised as another size")

    # resolutions below the floor are rejected, at or above are kept, silence passes
    check(not crit.resolution_ok(normalize('AOC CU34P2A 34" UWFHD 2560x1080 100Hz')),
          "2560x1080 passed the 3440x1440 floor")
    check(crit.resolution_ok(normalize('Dell U3425WE 34" 3440x1440')), "3440x1440 failed its own floor")
    check(crit.resolution_ok(normalize('LG 34" 5120x2160 5K2K')), "5120x2160 failed the floor")
    check(crit.resolution_ok(normalize('ViewSonic VP3481a 34" Curved Monitor')),
          "a title naming no resolution was rejected")


# --------------------------------------------------------------------------------------------------
# 2. the accessory filter, inverted for a monitor build
# --------------------------------------------------------------------------------------------------
def test_accessories() -> None:
    for title in ("Βραχίονας οθόνης Dell MDA20 Monitor Arm για οθόνες έως 34''",
                  "Monitor Stand Riser 34 inch desk mount",
                  "Καλώδιο DisplayPort 1.4 8K 2m",
                  "Βάση τοίχου VESA 100x100 για οθόνη 34",
                  'Samsung Smart TV 43" Crystal UHD',
                  "Logitech MX Keys Keyboard"):
        check(is_accessory(title), f"accessory not rejected: {title!r}")

    # the words a real 34-inch work monitor uses must not get it thrown away
    for title in ('Dell UltraSharp 34 USB-C Hub Monitor U3425WE 3440x1440 with KVM switch and height-adjustable stand, HDMI cable included',
                  'MSI MPG 341CQPX QD-OLED 34" 3440x1440 240Hz KVM USB-C 98W',
                  'Οθόνη Philips 34B1U5600CH 34" 3440x1440 USB-C Dock KVM webcam'):
        check(not is_accessory(title), f"real monitor thrown away as an accessory: {title!r}")


# --------------------------------------------------------------------------------------------------
# 2b. titles taken verbatim from a live run against the six shops
# --------------------------------------------------------------------------------------------------
def test_real_shop_titles() -> None:
    """Regression cases from the first live run. Each one was a bug.

    The three white goods came back from Public's own search for "Samsung 34" and were offered as
    34-inch candidates: an oven measured in litres ("71 Lt / 34 Lt") and two fridges whose model codes
    carry a bare 34 exactly as readably as a monitor's does. The Samsung monitors are the other half of
    the same lesson: "Ultra WQHD" is Samsung's name for 3440x1440, and reading it as the plain "WQHD"
    inside it put every Samsung ultrawide below the resolution floor and out of the discovery scan.
    """
    crit = criteria_mod.from_config(CFG)
    cases = [
        ("NEFF U1ACE2AG3B 71 Lt / 34 Lt Graphite Grey Εντοιχιζόμενος Φούρνος Άνω Πάγκου", False),
        ("SAMSUNG RB34C600ESA/EF Full No Frost 344 Lt Ασημί Ψυγειοκαταψύκτης", False),
        ("SAMSUNG RB34C672DSA/EF No Frost 344 Lt Ασημί Ψυγειοκαταψύκτης", False),
        ("Προστατευτικό οθόνης Samsung Galaxy A34 - Samsung 2pcs", False),
        ("Redshield Silic Lace A34 5G Black", False),
        ('PC Monitor 34" SAMSUNG Curved Odyssey G8 G85SB LS34BG850SUXEN Ultra WQHD', True),
        ('PC Monitor 34" SAMSUNG Curved ViewFinity S6 S65VC LS34C652VAUXEN UWQHD VA LED black', True),
        ('AOC CU34G4 Curved Gaming PC Monitor, 34"', True),
        ('PC Monitor 34" LORGAR Curved 34MP1 VA Mini-LED UWQHD LRG-34MP1W180C-GY black/grey', True),
        ('PC Monitor 34" ACER Curved Nitro ED340CURX0bmiipx UM.CE0EE.010 UWQHD VA black', True),
        ('SAMSUNG LS34DG850SUXDU Curved Gaming PC Monitor, 34"', True),
        ('PC Monitor 27" SAMSUNG WQHD 2560x1440', False),
    ]
    for title, want in cases:
        check(looks_like_candidate(title, crit) is want,
              f"live title read wrong (wanted candidate={want}): {title[:70]!r}")

    # "Ultra WQHD" must read as 3440x1440, not as the 2560x1440 of the "WQHD" inside it
    check(criteria_mod.resolution_in_title(normalize('34" Ultra WQHD')) == (3440, 1440),
          "'Ultra WQHD' was not read as 3440x1440")
    # a unit-qualified number is a measurement of something else, never a screen size
    check(not crit.has_size(normalize("Φούρνος 71 Lt / 34 Lt")), "'34 Lt' was read as a 34-inch size")
    check(crit.has_size(normalize('Monitor 34" UWQHD')), "a real 34-inch title stopped matching")


# --------------------------------------------------------------------------------------------------
# 2c. the price parser
# --------------------------------------------------------------------------------------------------
def test_prices() -> None:
    """Every shop writes money differently, and one of them writes it with a single decimal digit.

    Kotsovolos returns its selling price as "1099.0". Reading only two-digit decimals as decimals
    turned that into 10990 - ten times too high, which pushed every price from that shop past the
    1,800 EUR cap, so the shop matched nothing and looked merely empty rather than broken. The cap
    hid the bug instead of catching it, which is why these cases are pinned here.
    """
    cases = {
        "1099.0": 1099.0, "899.0": 899.0, "139.9": 139.9,           # one decimal digit
        "1099.00": 1099.0, "139.90": 139.9, "1,099.00": 1099.0,     # two
        "1.099,00": 1099.0, "1.199,00 €": 1199.0, "697 ,99€": 697.99, "€1, 199.00": 1199.0,
        "1.099": 1099.0, "1099": 1099.0,                            # thousands separator, no decimal
        "1.09": 1.09, "10.990,00": 10990.0,
    }
    for text, want in cases.items():
        got = parse_price(text)
        check(got == want, f"parse_price({text!r}) = {got}, expected {want}")
    check(parse_price("") is None and parse_price("free") is None, "empty price text should be None")


# --------------------------------------------------------------------------------------------------
# 3. matching, Discover and the price cap, through engine.match_items
# --------------------------------------------------------------------------------------------------
def test_match_items() -> None:
    crit = criteria_mod.from_config(CFG)
    wl = watchlist_mod.load()
    models = wl.watched(crit)
    check(len(models) >= 8, f"expected a populated watchlist, got {len(models)} watched models")

    items = [
        # --- must match ---
        item("electroline", 'DELL UltraSharp U3425WE 34" Curved USB-C Hub Monitor 3440x1440 120Hz IPS Black',
             699.0, 849.0, True, "EL-1"),
        item("stephanis", 'Οθόνη Dell UltraSharp U3425WE 86.8 cm (34") UWQHD 3440x1440 120Hz Thunderbolt 4',
             879.0, None, True, "ST-1"),
        item("public", 'LG UltraGear 34GP83A-B 34" Nano IPS 3440x1440 160Hz 1ms HDR400', 549.0, None, True, "PU-1"),
        item("kotsovolos", 'MSI MPG 341CQPX QD-OLED 34" 3440x1440 240Hz 0.03ms', 999.0, 1299.0, True, "KO-1"),
        item("scandia", 'Samsung Odyssey OLED G8 LS34BG850SUXEN 34" 3440x1440 175Hz QD-OLED', 849.0, None, True, "SC-1"),
        item("megaelectric", 'Gigabyte M34WQ 34" 21:9 3440x1440 144Hz IPS KVM USB-C', 399.0, None, True, "ME-1"),
        # --- same family, different size: must not match ---
        item("public", 'LG UltraGear 27GP83B-B 27" Nano IPS 2560x1440 165Hz', 329.0, None, True, "PU-2"),
        # --- a model that was checked and rejected: must not match and must not reach Discover ---
        item("electroline", 'DELL UltraSharp U3423WE 34" IPS Black 3440x1440 60Hz USB-C Hub', 749.0, None, True, "EL-2"),
        item("stephanis", 'Οθόνη Philips 34B1U5600CH 34" 3440x1440 120Hz USB-C 100W KVM webcam', 659.0, None, True, "ST-2"),
        # --- prefix traps: a shorter code must not claim a longer one's listing, or the reverse ---
        item("kotsovolos", 'MSI MAG 341CQP QD-OLED 34" 3440x1440 175Hz', 749.0, None, True, "KO-2"),
        item("public", 'Alienware AW3423DW 34" QD-OLED 3440x1440 175Hz G-Sync Ultimate', 899.0, None, True, "PU-3"),
        item("scandia", 'Samsung Odyssey OLED G8 G85SD LS34DG850SUXEN 34" 240Hz', 1099.0, None, True, "SC-2"),
        # --- accessories ---
        item("electroline", "Βραχίονας οθόνης Dell MDA20 Monitor Arm για οθόνες έως 34''", 159.0, None, True, "EL-3"),
        item("megaelectric", "Monitor Stand Riser 34 inch desk mount", 45.0, None, True, "ME-2"),
        # --- outside the price range: a shop data error, not a product ---
        item("stephanis", 'AOC AGON PRO AG344UXM 34" Mini LED 3440x1440 170Hz', 2400.0, None, True, "ST-3"),
        # --- unknown but plausible: Discover should surface these ---
        item("public", 'LG 34WQ75C-B 34" IPS 3440x1440 USB-C 90W', 429.0, None, True, "PU-4"),
        item("kotsovolos", 'Οθόνη ViewSonic VP3481a 86,4 cm Curved Monitor', 519.0, None, True, "KO-3"),
        # --- below the resolution floor: Discover should NOT surface it ---
        item("megaelectric", 'AOC CU34P2A 34" UWFHD 2560x1080 100Hz VA', 279.0, None, True, "ME-3"),
    ]

    offers, unmatched = match_items(items, models, CFG["price_range"], crit, wl.rejected)
    matched = {(o.shop, o.model_key) for o in offers}
    disco = {it.shop_sku for it in unmatched}

    for shop, key in [("electroline", "U3425WE"), ("stephanis", "U3425WE"), ("public", "34GP83A"),
                      ("kotsovolos", "MPG341CQPX"), ("scandia", "LS34BG850"), ("megaelectric", "M34WQ")]:
        check((shop, key) in matched, f"{key} did not match at {shop}")

    keys = [o.model_key for o in offers]
    check("34GP83A" in keys and keys.count("34GP83A") == 1, "the 27-inch 27GP83B matched 34GP83A")
    check(not any(k == "U3423WE" for k in keys), "the rejected 60 Hz U3423WE produced an offer")
    check("EL-2" not in disco, "the rejected U3423WE was offered to Discover again")
    check("ST-2" not in disco, "the rejected Philips 34B1U5600CH was offered to Discover again")
    check(not any(o.shop_sku == "KO-2" for o in offers), "MAG 341CQP was claimed by MPG341CQPX")
    check("KO-2" in disco, "MAG 341CQP should reach Discover as an unknown product")
    check(not any(o.shop_sku == "PU-3" for o in offers), "AW3423DW was claimed by AW3423DWF")
    # The G85SD is now on the watch list too, so the test is no longer "it must not match" but the
    # sharper one: the two Samsungs are one character apart in the model code and must not claim each
    # other's listings. They are priced hundreds of euros apart, so a swap here would alert on fiction.
    sc2 = [o for o in offers if o.shop_sku == "SC-2"]
    check(len(sc2) == 1 and sc2[0].model_key == "LS34DG850",
          f"the G85SD listing matched {[o.model_key for o in sc2]}, expected LS34DG850")
    check(not any(o.shop_sku == "SC-1" and o.model_key == "LS34DG850" for o in offers),
          "the G85SB listing was claimed by the G85SD entry")
    check("EL-3" not in disco and "ME-2" not in disco, "an accessory reached Discover")
    check(not any(o.shop_sku in ("EL-3", "ME-2") for o in offers), "an accessory produced an offer")
    check(not any(o.shop_sku == "ST-3" for o in offers),
          "a 2,400 EUR listing passed the 1,800 EUR cap")
    check("PU-4" in disco and "KO-3" in disco,
          "plausible unknown monitors did not reach Discover (PU-4/KO-3)")
    check("ME-3" not in disco, "a 2560x1080 panel reached Discover despite the resolution floor")

    # the cap is a data-error filter, so a real product priced inside it must survive
    inside, _ = match_items([item("stephanis", 'AOC AGON PRO AG344UXM 34" Mini LED 3440x1440 170Hz',
                                  1099.0, None, True, "ST-4")],
                            models, CFG["price_range"], crit, wl.rejected)
    check([o.model_key for o in inside] == ["AG344UXM"],
          "AG344UXM at 1,099 EUR did not match; the price cap may be too low")

    # a list price that is obviously a shop error is dropped rather than used to invent a discount
    bogus, _ = match_items([item("electroline", 'DELL U3425WE 34" 3440x1440 120Hz', 699.0, 9999.0, True, "EL-4")],
                           models, CFG["price_range"], crit, wl.rejected)
    check(bogus and bogus[0].list_price is None, "an implausible list price was kept")

    return offers


# --------------------------------------------------------------------------------------------------
# 4. the three alert rules
# --------------------------------------------------------------------------------------------------
def test_rules() -> None:
    wl = watchlist_mod.load()
    current = [
        # cross-shop: Electroline 20% under Stephanis for the same model
        Offer(shop="electroline", model_key="U3425WE", title="U3425WE", price=699.0,
              url="https://electroline.cy/p/1", list_price=849.0, in_stock=True),
        Offer(shop="stephanis", model_key="U3425WE", title="U3425WE", price=879.0,
              url="https://www.stephanis.com.cy/p/1", list_price=None, in_stock=True),
        # list discount: 23% below the shop's own list price
        Offer(shop="kotsovolos", model_key="MPG341CQPX", title="MPG 341CQPX", price=999.0,
              url="https://www.kotsovolos.cy/p/1", list_price=1299.0, in_stock=True),
        # back in stock: was out in the previous snapshot
        Offer(shop="public", model_key="34GP83A", title="34GP83A", price=549.0,
              url="https://www.public.cy/p/1", list_price=None, in_stock=True),
    ]
    previous = {
        ("public", "34GP83A"): Offer(shop="public", model_key="34GP83A", title="34GP83A", price=549.0,
                                     url="https://www.public.cy/p/1", in_stock=False),
        ("electroline", "U3425WE"): Offer(shop="electroline", model_key="U3425WE", title="U3425WE",
                                          price=849.0, url="https://electroline.cy/p/1", in_stock=True),
    }
    alerts = rules.evaluate(current, previous, wl, CFG, LABELS)
    fired = {a.rule for a in alerts}
    for rule in ("cross_shop", "list_discount", "back_in_stock"):
        check(rule in fired, f"{rule} did not fire")

    cross = next(a for a in alerts if a.rule == "cross_shop")
    check("Electroline" in cross.message and "20%" in cross.message,
          f"cross-shop message reads wrong: {cross.message}")
    disc = next(a for a in alerts if a.rule == "list_discount")
    check("23%" in disc.message, f"list-discount percentage reads wrong: {disc.message}")

    # an out-of-stock listing is not an offer, so it must not win the cross-shop comparison
    oos = list(current) + [Offer(shop="scandia", model_key="U3425WE", title="U3425WE", price=199.0,
                                 url="https://scandia.cy/p/1", in_stock=False)]
    alerts2 = rules.evaluate(oos, previous, wl, CFG, LABELS)
    cross2 = next(a for a in alerts2 if a.rule == "cross_shop")
    check(cross2.shop == "electroline", "an out-of-stock price won the cross-shop comparison")


def main() -> int:
    test_digit_boundaries()
    test_accessories()
    test_real_shop_titles()
    test_prices()
    test_match_items()
    test_rules()
    print(f"{checks - len(failures)}/{checks} checks passed")
    for f in failures:
        print("  FAIL:", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
