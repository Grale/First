"""What counts as a monitor worth watching: size class, panel technology, resolution and the spec floor.

Everything the buyer's requirements touch lives here and is driven by the config "criteria" block, so a
change of requirements is a settings edit rather than a hunt through the matcher, the engine and the shops.

    sizes               screen sizes in inches that qualify; a size class may hold more than one size
                        because neighbouring ultrawides sit in the same bracket (34/38/39)
    panels              panel families that qualify, keys of PANEL_FAMILIES
    min_hz              lowest native refresh rate that qualifies
    min_width           lowest native horizontal resolution that qualifies
    min_height          lowest native vertical resolution that qualifies
    require_height_adjust   a height-adjustable stand must be present to qualify
    require_usb_c_pd_w  minimum USB-C power delivery in watts to qualify (0 = not required)
    require_kvm         a built-in KVM must be present to qualify (otherwise it only earns fit points)
    require_vrr         VRR must be present to qualify (otherwise it only earns fit points)

A monitor title is a different animal from a TV title. A TV is sold by its panel brand ("Neo QLED",
"OLED evo"), so a TV title almost always names the family. Monitor titles frequently name no panel at
all ("DELL U3425WE 34 LED MONITOR"), so a family filter that demands a match would hide most of the
market from the discovery scan. The family test is therefore exclusive rather than inclusive: a title
fails only when it names a family that is *not* wanted and names no wanted family. The same reasoning
applies to resolution.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from . import config as config_mod

# Greek accented capitals do not fold to their unaccented forms on their own: "Καλώδιο".upper() is
# "ΚΑΛΏΔΙΟ", which does not equal "ΚΑΛΩΔΙΟ". Cyprus shop titles accent inconsistently - the same shop
# writes "Οθόνη" and "ΟΘΟΝΗ" on different pages - so every keyword comparison folds accents first.
# Without this, half the Greek accessory keywords silently never match.
_GREEK_FOLD = str.maketrans({
    "Ά": "Α", "Έ": "Ε", "Ή": "Η", "Ί": "Ι", "Ό": "Ο", "Ύ": "Υ", "Ώ": "Ω",
    "ά": "α", "έ": "ε", "ή": "η", "ί": "ι", "ό": "ο", "ύ": "υ", "ώ": "ω",
    "Ϊ": "Ι", "Ϋ": "Υ", "ϊ": "ι", "ϋ": "υ", "ΐ": "ι", "ΰ": "υ", "ς": "σ",
})


def fold_greek(text: str) -> str:
    """Upper-case `text` with Greek accents and final sigma folded away."""
    return (text or "").translate(_GREEK_FOLD).upper().translate(_GREEK_FOLD)

# Every size a monitor listing may name, in the steps monitors are actually sold in. A title that names
# one of these and never a wanted size is a different variant of the same model. 26, 27.9 and the like
# are left out: shops round them. 16/17/19/20 are left out because they would match inside model codes
# far more often than they would name a panel ("LS27AG320", "P2419H").
ALL_SIZES = (21, 22, 23, 24, 25, 27, 28, 29, 30, 31, 32, 34, 38, 39, 40, 42, 45, 48, 49, 57)

# pattern: matched against a normalised title (upper-case alphanumerics, single spaces)
# terms:   query words for the shops that are searched rather than listed
#
# "IPS" and "VA" need boundary guards that "OLED" does not: ViewSonic ships a VA-prefixed model range
# ("VA3456"), and VALUE/NOVA/VIVA all contain VA. A bare substring test would claim them all.
PANEL_FAMILIES: dict[str, dict[str, Any]] = {
    "oled": {
        "label": "OLED",
        "pattern": r"OLED",                 # covers OLED, QD-OLED and W-OLED once normalised
        "terms": ("OLED",),
    },
    "miniled": {
        "label": "Mini LED",
        "pattern": r"MINI ?LED|MINILED|QD MINI",
        "terms": ("Mini LED", "MiniLED"),
    },
    "ips": {
        "label": "IPS",
        "pattern": r"(?<![A-Z0-9])(NANO ?IPS|FAST ?IPS|IPS BLACK|IPS)(?![A-Z0-9])",
        "terms": ("IPS",),
    },
    "va": {
        "label": "VA",
        "pattern": r"(?<![A-Z0-9])(AMVA|VA PANEL|PANEL VA)(?![A-Z0-9])",
        "terms": ("VA",),
    },
    "any": {
        "label": "any panel",
        "pattern": "",                      # no filter at all
        "terms": ("Monitor",),
    },
}

# Product words for the shops that answer queries instead of listing a category, in both languages.
PRODUCT_TERMS = ("Monitor", "Οθόνη", "Ultrawide")

# Marketing resolution names, for the listings that give a name and never a pixel count. Longest first
# so UWQHD is read before QHD could be found inside it.
RESOLUTION_NAMES: tuple[tuple[str, tuple[int, int]], ...] = (
    # Samsung sells 3440x1440 as "Ultra WQHD" and LG as "UWQHD". Both have to be read before the bare
    # "WQHD" inside them, or a 34-inch ultrawide is taken for a 2560x1440 panel and drops below the
    # resolution floor - which silently hid every Samsung ultrawide from the discovery scan.
    ("ULTRA WQHD", (3440, 1440)),
    ("ULTRA WIDE QHD", (3440, 1440)),
    ("ULTRA WFHD", (2560, 1080)),
    ("5K2K", (5120, 2160)),
    ("UWQHD", (3440, 1440)),
    ("UWFHD", (2560, 1080)),
    ("WUHD", (5120, 2160)),
    ("WQHD", (2560, 1440)),
    ("WFHD", (2560, 1080)),
    ("QHD", (2560, 1440)),
    ("UHD", (3840, 2160)),
    ("FHD", (1920, 1080)),
)
# A pixel count as a title writes it. `normalize` keeps the "x" (it is alphanumeric), so "3440x1440"
# arrives as the single token "3440X1440"; "3440 x 1440" arrives spaced. Both forms are accepted.
_RES_PX_RE = re.compile(r"(?<![0-9])(\d{3,4}) ?[X\*] ?(\d{3,4})(?![0-9])")
_RES_NAME_RE = re.compile("|".join(re.escape(tok) for tok, _ in RESOLUTION_NAMES))
_RES_NAME_MAP = dict(RESOLUTION_NAMES)

# Aspect ratios, which normalise to a bare number pair ("21:9" -> "21 9"). Several of those numbers are
# monitor sizes in their own right (21, 32, 16), so they are stripped before any size test: without this
# every 21:9 ultrawide would read as naming a 21-inch panel, and a 32:9 superultrawide as a 32-inch one.
_ASPECT_RE = re.compile(r"(?<![0-9])(21 9|32 9|16 9|16 10|4 3|5 4|21 10)(?![0-9])")

# A number carrying a unit is a measurement of something else. Shops that answer searches return the
# whole catalogue for "34", and an oven listed as "71 Lt / 34 Lt" was read as a 34-inch panel until
# this was added. Inches and centimetres are deliberately absent: those ARE sizes, and the centimetre
# form is read separately by sizes_from_cm, which runs before this strips anything.
_UNIT_RE = re.compile(
    r"(?<![0-9])\d+(?: \d+)? (LT|L|ML|KG|GR|G|GB|TB|MB|KWH|KW|W|V|A|HZ|MM|M|DB|RPM|BAR|LM|LUMEN|"
    r"ΛΙΤΡΑ|ΛΤ|ΚΙΛΑ)(?![A-Z0-9])")


@lru_cache(maxsize=32)
def _size_res(sizes: tuple[int, ...]) -> tuple[re.Pattern, re.Pattern]:
    """(wanted, other) size patterns. Longest alternatives first so 115 never matches as 11.

    The digit-boundary lookarounds are what keep "34" from matching inside "3440x1440", "165Hz" or a
    model code's resolution suffix. They are tested in tests/test_titles.py.
    """
    def alt(values) -> str:
        return "|".join(str(v) for v in sorted(values, key=lambda v: (-len(str(v)), -v)))

    wanted = sorted(set(sizes))
    other = sorted(set(ALL_SIZES) - set(wanted))
    w_re = re.compile(rf"(?<![0-9])({alt(wanted)})(?![0-9])") if wanted else re.compile(r"(?!x)x")
    o_re = re.compile(rf"(?<![0-9])({alt(other)})(?![0-9])") if other else re.compile(r"(?!x)x")
    return w_re, o_re


@lru_cache(maxsize=32)
def _panel_re(panels: tuple[str, ...]) -> Optional[re.Pattern]:
    if not panels or "any" in panels:
        return None
    parts = [PANEL_FAMILIES[p]["pattern"] for p in panels if PANEL_FAMILIES.get(p, {}).get("pattern")]
    return re.compile("|".join(parts)) if parts else None


@lru_cache(maxsize=32)
def _other_panel_re(panels: tuple[str, ...]) -> Optional[re.Pattern]:
    """Families that are *not* wanted, so a title naming one is a different product."""
    if not panels or "any" in panels:
        return None
    parts = [fam["pattern"] for key, fam in PANEL_FAMILIES.items()
             if key not in panels and key != "any" and fam.get("pattern")]
    return re.compile("|".join(parts)) if parts else None


def strip_aspect(norm_title: str) -> str:
    """The title with aspect-ratio pairs and unit-qualified numbers blanked out.

    Both would otherwise be read as screen sizes: "21:9" as a 21-inch panel, "34 Lt" as a 34-inch one.
    """
    return _UNIT_RE.sub(" ", _ASPECT_RE.sub(" ", norm_title))


def resolution_px_in_title(norm_title: str) -> Optional[tuple[int, int]]:
    """The highest explicit pixel count a title states, or None.

    Separate from the marketing names on purpose. A pixel count is something only a display's own
    listing carries, which makes it a reliable signal that a title is a monitor rather than one of its
    accessories. "UHD" and "QHD" are not: televisions, projectors and cables print them too.
    """
    found: list[tuple[int, int]] = []
    for m in _RES_PX_RE.finditer(norm_title):
        w, h = int(m.group(1)), int(m.group(2))
        if w >= 640 and h >= 480:       # a pixel count, not a part number, a VESA size or a price
            found.append((w, h))
    return max(found, key=lambda wh: wh[0] * wh[1]) if found else None


def resolution_in_title(norm_title: str) -> Optional[tuple[int, int]]:
    """The highest native resolution a title names, by pixel count or by marketing name, or None.

    Highest, not first, because a title may carry both its own resolution and a lesser one it supports
    ("3440x1440 ... 2560x1080 compatible"); the panel is the better of the two.
    """
    found: list[tuple[int, int]] = []
    px = resolution_px_in_title(norm_title)
    if px:
        found.append(px)
    for m in _RES_NAME_RE.finditer(norm_title):
        found.append(_RES_NAME_MAP[m.group(0)])
    return max(found, key=lambda wh: wh[0] * wh[1]) if found else None


def _cm_to_inch(cm: float) -> float:
    return cm / 2.54


_CM_RE = re.compile(r"(?<![0-9])(\d{2,3})(?:[ .,](\d))? ?CM(?![A-Z0-9])")


def sizes_from_cm(norm_title: str) -> list[int]:
    """Inch sizes implied by a centimetre figure in the title ("86 4 CM" -> 34).

    Monitor listings in Cyprus sometimes give the diagonal only in centimetres. Rounded to the nearest
    inch, with a half-inch tolerance either way, because 34" is quoted as both 86.4 cm and 86 cm.
    """
    out: list[int] = []
    for m in _CM_RE.finditer(norm_title):
        whole, frac = m.group(1), m.group(2)
        cm = float(whole) + (float(frac) / 10.0 if frac else 0.0)
        inch = _cm_to_inch(cm)
        for s in ALL_SIZES:
            if abs(inch - s) <= 0.5:
                out.append(s)
    return out


@dataclass(frozen=True)
class Criteria:
    sizes: tuple[int, ...] = (34,)
    panels: tuple[str, ...] = ("oled", "miniled", "ips")
    min_hz: int = 100
    min_width: int = 3440
    min_height: int = 1440
    require_height_adjust: bool = True
    require_usb_c_pd_w: int = 0
    require_kvm: bool = False
    require_vrr: bool = False

    # ---------------- title tests ----------------
    def has_size(self, norm_title: str) -> bool:
        """The title names one of the wanted sizes, in inches or as a centimetre diagonal."""
        t = strip_aspect(norm_title)
        if _size_res(self.sizes)[0].search(t):
            return True
        return any(s in self.sizes for s in sizes_from_cm(t))

    def names_other_size(self, norm_title: str) -> bool:
        """The title names a size that is not wanted, so it is a different variant."""
        t = strip_aspect(norm_title)
        if _size_res(self.sizes)[1].search(t):
            return True
        cm_sizes = sizes_from_cm(t)
        return bool(cm_sizes) and not any(s in self.sizes for s in cm_sizes)

    def panel_ok(self, norm_title: str) -> bool:
        """The title does not rule itself out on panel family.

        True when it names a wanted family, and also true when it names no family at all: most monitor
        titles do not state the panel. Only a title that names an unwanted family and no wanted one fails.
        """
        wanted = _panel_re(self.panels)
        if wanted is None:
            return True
        if wanted.search(norm_title):
            return True
        other = _other_panel_re(self.panels)
        return not (other and other.search(norm_title))

    def resolution_ok(self, norm_title: str) -> bool:
        """The title does not name a resolution below the floor. Silence passes, as above."""
        res = resolution_in_title(norm_title)
        if res is None:
            return True
        w, h = res
        return w >= self.min_width and h >= self.min_height

    # ---------------- spec tests ----------------
    def spec_problems(self, hz: Optional[int] = None, width: Optional[int] = None,
                      height: Optional[int] = None, height_adjust: Optional[bool] = None,
                      usb_c_pd_w: Optional[int] = None, kvm: Optional[bool] = None,
                      vrr: Optional[bool] = None) -> list[str]:
        """Why these specs fall short of the floor; empty when they qualify."""
        out: list[str] = []
        if not hz or hz < self.min_hz:
            out.append(f"{hz if hz else 'unknown'} Hz panel, floor is {self.min_hz} Hz")
        if not width or not height:
            out.append("resolution unknown")
        elif width < self.min_width or height < self.min_height:
            out.append(f"{width}x{height}, floor is {self.min_width}x{self.min_height}")
        # A requirement that is unverified is reported as unverified, never as absent. The two land in
        # the same place - the entry does not qualify - but the reason a model was set aside has to be
        # true, or the rejected list quietly turns into a list of libels about real products.
        if self.require_height_adjust:
            if height_adjust is None:
                out.append("height-adjustable stand unverified")
            elif not height_adjust:
                out.append("no height-adjustable stand")
        if self.require_usb_c_pd_w:
            if usb_c_pd_w is None:
                out.append(f"USB-C power delivery unverified, floor is {self.require_usb_c_pd_w} W")
            elif not usb_c_pd_w:
                out.append(f"no USB-C power delivery, floor is {self.require_usb_c_pd_w} W")
            elif usb_c_pd_w < self.require_usb_c_pd_w:
                out.append(f"USB-C PD {usb_c_pd_w} W, floor is {self.require_usb_c_pd_w} W")
        if self.require_kvm:
            out.append("KVM unverified" if kvm is None else ("" if kvm else "no KVM"))
        if self.require_vrr:
            out.append("VRR unverified" if vrr is None else ("" if vrr else "no VRR"))
        return [o for o in out if o]

    def specs_qualify(self, *a, **kw) -> bool:
        return not self.spec_problems(*a, **kw)

    # ---------------- labels and queries ----------------
    @property
    def size_label(self) -> str:
        return "/".join(str(s) for s in sorted(set(self.sizes))) + '"'

    @property
    def panel_label(self) -> str:
        names = [PANEL_FAMILIES[p]["label"] for p in self.panels if p in PANEL_FAMILIES]
        if not names:
            return "any panel"
        return names[0] if len(names) == 1 else " or ".join([", ".join(names[:-1]), names[-1]])

    @property
    def resolution_label(self) -> str:
        return f"{self.min_width}×{self.min_height}"

    @property
    def spec_label(self) -> str:
        bits = [f"native {self.min_hz} Hz or more", f"{self.resolution_label} or higher"]
        if self.require_height_adjust:
            bits.append("height-adjustable stand")
        if self.require_usb_c_pd_w:
            bits.append(f"USB-C PD {self.require_usb_c_pd_w} W or more")
        if self.require_kvm:
            bits.append("KVM")
        if self.require_vrr:
            bits.append("VRR")
        return ", ".join(bits)

    @property
    def label(self) -> str:
        return f"{self.size_label} {self.panel_label}"

    def panel_terms(self) -> list[str]:
        terms: list[str] = []
        for p in self.panels:
            for t in PANEL_FAMILIES.get(p, {}).get("terms", ()):
                if t not in terms:
                    terms.append(t)
        return terms

    def discovery_queries(self, brands: tuple[str, ...] = ()) -> list[str]:
        """Search terms for the shops that answer queries instead of listing a category.

        Brand-and-size is the query that actually works for monitors: the model codes carry the size at
        the front ("34GP63A", "U3423WE"), so a brand plus "34" reaches them, while panel words only
        reach the listings that bother to name the panel.
        """
        out: list[str] = []
        for size in sorted(set(self.sizes)):
            for term in (*PRODUCT_TERMS, *self.panel_terms()):
                out.append(f"{term} {size}")
            for brand in brands:
                out.append(f"{brand} {size}")
        return out


def from_config(cfg: dict) -> Criteria:
    d = (cfg or {}).get("criteria") or {}
    defaults = Criteria()
    sizes = tuple(int(s) for s in (d.get("sizes") or defaults.sizes))
    panels = tuple(str(p).strip().lower() for p in (d.get("panels") or defaults.panels)
                   if str(p).strip().lower() in PANEL_FAMILIES)
    return Criteria(
        sizes=sizes or defaults.sizes,
        panels=panels or defaults.panels,
        min_hz=int(d.get("min_hz", defaults.min_hz) or 0),
        min_width=int(d.get("min_width", defaults.min_width) or 0),
        min_height=int(d.get("min_height", defaults.min_height) or 0),
        require_height_adjust=bool(d.get("require_height_adjust", defaults.require_height_adjust)),
        require_usb_c_pd_w=int(d.get("require_usb_c_pd_w", defaults.require_usb_c_pd_w) or 0),
        require_kvm=bool(d.get("require_kvm", defaults.require_kvm)),
        require_vrr=bool(d.get("require_vrr", defaults.require_vrr)),
    )


def active() -> Criteria:
    """The criteria in the saved config. Build once per run and pass it down; this reads the file."""
    return from_config(config_mod.load())
