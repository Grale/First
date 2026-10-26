"""Match shop product titles to watchlist models.

Rules:
- Title and aliases are normalised to upper-case alphanumerics separated by single spaces.
- An alias matches when it appears in the title either as whole words or embedded in a longer
  code with no spaces (so "34GP63A" matches "LG34GP63AB", "U3425WE" matches "DELLU3425WE").
- The title (or the alias) must carry one of the wanted size markers, and accessories are rejected.
- When several models match, the longest matching alias wins. Rejected models take part as
  negatives, so "LG 34GP63A" is claimed by 34GP63A rather than by a shorter 34GP6 alias.

Which sizes, panel families and resolutions count comes from monbot.criteria, not from this module.
"""
from __future__ import annotations
import re
from typing import Iterable, Optional

from .criteria import Criteria, fold_greek, resolution_px_in_title
from .watchlist import Model, Rejected

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")

# Things to throw away. For a monitor build this list is the inverse of the TV build's: there, a monitor
# was the false positive and "MONITOR"/"ΟΘΟΝΗ Η/Υ" were rejected outright. Here a monitor is the product,
# and what must go are monitor peripherals and the televisions that share the shop aisle.
#
# Every marker is either a multi-word phrase or a word that cannot appear in a monitor's own title. That
# restraint is deliberate: "HUB", "DOCK" and "KVM" are all words real 34-inch work monitors advertise
# ("UltraSharp 34 USB-C Hub Monitor", "Thunderbolt Dock", "built-in KVM"), so none of them can be a
# reject word on its own. The risk here is asymmetric - throwing away a real monitor loses a product
# forever, while letting an accessory through only adds one line to the Discover list.
_ACCESSORY = (
    # mounting and support
    "MONITOR ARM", "MONITOR STAND", "MONITOR MOUNT", "DESK MOUNT", "DESK STAND", "WALL MOUNT",
    "VESA MOUNT", "VESA ADAPTER", "VESA KIT", "MONITOR RISER", "LAPTOP STAND",
    "ΒΡΑΧΙΟΝΑΣ", "ΒΑΣΗ ΟΘΟΝΗΣ", "ΒΑΣΗ ΤΟΙΧΟΥ", "ΒΑΣΗ ΣΤΗΡΙΞΗΣ", "ΕΠΙΤΟΙΧΙΑ ΒΑΣΗ",
    # docks, switches and hubs sold as their own product
    "DOCKING STATION", "KVM SWITCH BOX", "USB SWITCH", "HDMI SWITCH", "HDMI SPLITTER",
    "DISPLAYPORT SPLITTER", "SIGNAL EXTENDER",
    # cables, adapters, power
    "CABLE", "ΚΑΛΩΔΙΟ", "ADAPTER", "ΑΝΤΑΠΤΟΡΑΣ", "ΜΕΤΑΤΡΟΠΕΑΣ", "POWER SUPPLY", "ΤΡΟΦΟΔΟΤΙΚΟ",
    "CHARGER", "ΦΟΡΤΙΣΤΗΣ",
    # input devices and other desk peripherals
    "KEYBOARD", "ΠΛΗΚΤΡΟΛΟΓΙΟ", "MOUSE", "ΠΟΝΤΙΚΙ", "MOUSEPAD", "MOUSE PAD", "WEBCAM", "ΚΑΜΕΡΑ",
    "HEADSET", "ΑΚΟΥΣΤΙΚΑ", "SOUNDBAR", "SOUND BAR", "ΗΧΕΙΑ", "SPEAKER", "MICROPHONE", "ΜΙΚΡΟΦΩΝΟ",
    "LIGHT BAR", "SCREEN BAR", "PRIVACY FILTER", "SCREEN PROTECTOR", "ΚΑΘΑΡΙΣΤΗΣ", "CLEANING KIT",
    "REMOTE", "ΤΗΛΕΧΕΙΡΙΣΤΗΡΙΟ", "CARRY CASE", "ΘΗΚΗ",
    # neighbouring product categories that are not monitors
    "SMART TV", "TELEVISION", "ΤΗΛΕΟΡΑΣΗ", "PROJECTOR", "ΠΡΟΒΟΛΕΑΣ", "TABLET", "SMARTPHONE",
    "LAPTOP", "NOTEBOOK", "DESKTOP PC", "ALL IN ONE PC", "MINI PC", "PRINTER", "ΕΚΤΥΠΩΤΗΣ",
    # white goods. The two search-driven shops answer "<brand> 34" with the whole catalogue, and a
    # fridge model code carries a bare 34 as readably as a monitor's does ("RB34C600ESA"), so the
    # product category is the only thing that separates them.
    "ΦΟΥΡΝΟΣ", "ΦΟΥΡΝΟΙ", "ΚΟΥΖΙΝΑ", "ΕΣΤΙΑ", "ΕΣΤΙΕΣ", "ΑΠΟΡΡΟΦΗΤΗΡΑΣ", "ΜΙΚΡΟΚΥΜΑΤΩΝ",
    "ΨΥΓΕΙΟ", "ΚΑΤΑΨΥΚΤΗΣ", "ΠΛΥΝΤΗΡΙΟ", "ΣΤΕΓΝΩΤΗΡΙΟ", "ΚΛΙΜΑΤΙΣΤΙΚΟ", "ΣΚΟΥΠΑ", "ΚΑΦΕΤΙΕΡΑ",
    "OVEN", "COOKER", "HOB", "EXTRACTOR HOOD", "MICROWAVE", "FRIDGE", "REFRIGERATOR", "FREEZER",
    "WASHING MACHINE", "DISHWASHER", "TUMBLE DRYER", "AIR CONDITIONER", "VACUUM CLEANER",
)


def normalize(text: str) -> str:
    t = fold_greek(text)
    t = t.replace("&QUOT;", '"').replace("’", "'").replace("”", '"')
    t = _NON_ALNUM.sub(" ", t)
    return " ".join(t.split())


def _alias_hits(norm_title: str, alias: str) -> bool:
    a = normalize(alias)
    if not a:
        return False
    if f" {a} " in f" {norm_title} ":
        return True
    # embedded in a longer code: compare with spaces removed
    if " " not in a and a in norm_title.replace(" ", ""):
        return True
    return False


def is_accessory(title: str) -> bool:
    """True when the title is a peripheral or a different product category rather than a monitor.

    An explicit pixel count vetoes the verdict. Accessory listings do not carry one, while monitor
    listings very often carry both a pixel count and a word from the list above ("34 UWQHD 3440x1440
    monitor with USB-C hub and height-adjustable stand, HDMI cable included").
    """
    up = fold_greek(title)
    if not any(k in up for k in _ACCESSORY):
        return False
    # Only an explicit pixel count vetoes the verdict. A marketing name would not do: televisions and
    # projectors print "UHD" as freely as monitors do, and "Smart TV ... UHD" must stay rejected.
    return resolution_px_in_title(normalize(title)) is None


MIN_SELF_IDENTIFYING_ALIAS = 6


def match_aliases(title: str, aliases: Iterable[str], crit: Criteria,
                  model_size: Optional[float] = None) -> Optional[str]:
    """Return the longest alias that matches the title, or None."""
    if is_accessory(title):
        return None
    norm = normalize(title)
    best: Optional[str] = None
    for alias in aliases:
        if _alias_hits(norm, alias):
            if best is None or len(normalize(alias)) > len(normalize(best)):
                best = alias
    if best is None:
        return None
    alias_norm = normalize(best)
    # size gate: the alias itself may carry the size (34GP83A, LS34BG850, Y34WZ30) or the title must
    if not crit.has_size(alias_norm) and not crit.has_size(norm):
        # Some codes hide the size from the digit-boundary rule: Dell's U3425WE spells 34 inside
        # "3425" and Asus's PA348CGV inside "348", so neither reads as a 34-inch marker, correctly -
        # the rule cannot tell a size from a year or a part number. But a code that long identifies
        # exactly one panel, and the watchlist already knows how big that panel is. Where it does,
        # trust the watchlist rather than requiring the shop to repeat the size in the title, which
        # the shorter Kotsovolos and Public titles often do not.
        size_known = model_size is not None and int(round(model_size)) in crit.sizes
        if not (size_known and len(alias_norm.replace(" ", "")) >= MIN_SELF_IDENTIFYING_ALIAS):
            return None
    # a title that names another size and never a wanted one is a different variant
    if not crit.has_size(norm) and crit.names_other_size(norm):
        return None
    return best


def match_model(title: str, model: Model, crit: Criteria) -> Optional[str]:
    return match_aliases(title, model.all_aliases(), crit, model_size=model.size_inch)


def best_match(title: str, models: Iterable[Model], crit: Criteria,
               negatives: Iterable[Rejected] = ()) -> Optional[Model]:
    """Best watchlist model for a title; None when nothing matches or a rejected model matches better."""
    best_model: Optional[Model] = None
    best_len = -1
    for m in models:
        alias = match_model(title, m, crit)
        if alias is not None:
            ln = len(normalize(alias))
            if ln > best_len:
                best_len, best_model = ln, m
    if best_model is None:
        return None
    for r in negatives:
        alias = match_aliases(title, [r.model_key, *r.aliases], crit)
        if alias is not None and len(normalize(alias)) >= best_len:
            return None
    return best_model


def matches_rejected(title: str, negatives: Iterable[Rejected], crit: Criteria) -> bool:
    return any(match_aliases(title, [r.model_key, *r.aliases], crit) is not None for r in negatives)


def looks_like_candidate(title: str, crit: Criteria) -> bool:
    """Loose filter used by the discovery scan: wanted size, and nothing that rules the title out.

    Panel family and resolution are tested exclusively rather than inclusively (see monbot.criteria):
    most monitor listings name neither, and demanding either one would hide the market from Discover.
    """
    if is_accessory(title):
        return False
    norm = normalize(title)
    return crit.has_size(norm) and crit.panel_ok(norm) and crit.resolution_ok(norm)
