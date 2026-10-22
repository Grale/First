"""What counts as a TV worth watching: size class, panel technology and the spec floor.

Everything the buyer's requirements touch lives here and is driven by the config "criteria" block, so a
change of requirements is a settings edit rather than a hunt through the matcher, the engine and the shops.

    sizes            screen sizes in inches that qualify; a size class may hold more than one size because
                     the panel lines do not line up (OLED is sold at 77", Mini LED at 75")
    panels           panel/backlight families that qualify, keys of PANEL_FAMILIES
    min_hz           lowest native refresh rate that qualifies
    require_vrr      VRR must be present to qualify (otherwise it only earns fit points)
    require_hdmi21   a full HDMI 2.1 input must be present to qualify (otherwise it only earns fit points)
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from . import config as config_mod

# Every size a shop title may name. A title that names one of these and never a wanted size is a different
# variant of the same model. 80 is left out on purpose: it is not a European size, and "A80L", "W80" and
# "QNED80" would all read as one.
ALL_SIZES = (24, 28, 32, 40, 42, 43, 48, 50, 55, 58, 60, 65, 70, 75, 77, 83, 85, 86, 90, 97, 98, 100, 115)

# pattern: matched against a normalised title (upper-case alphanumerics, single spaces)
# terms:   query words for the shops that are searched rather than listed
PANEL_FAMILIES: dict[str, dict[str, Any]] = {
    "oled": {
        "label": "OLED",
        "pattern": r"OLED",                 # covers OLED, QD-OLED and W-OLED once normalised
        "terms": ("OLED",),
    },
    "miniled": {
        "label": "Mini LED",
        "pattern": r"MINI ?LED|MINILED|QD MINI|SQD|RGB MINI|NEO QLED|QNED|ULED",
        "terms": ("Mini LED", "MiniLED", "Neo QLED", "QNED", "ULED", "RGB Mini LED"),
    },
    "qled": {
        "label": "QLED",
        "pattern": r"QLED|QD LED|QUANTUM",
        "terms": ("QLED",),
    },
    "led": {
        "label": "LED",
        "pattern": r"LED|LCD",
        "terms": ("LED TV",),
    },
    "any": {
        "label": "any panel",
        "pattern": "",                      # no filter at all
        "terms": ("TV",),
    },
}


@lru_cache(maxsize=32)
def _size_res(sizes: tuple[int, ...]) -> tuple[re.Pattern, re.Pattern]:
    """(wanted, other) size patterns. Longest alternatives first so 115 never matches as 11."""
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


@dataclass(frozen=True)
class Criteria:
    sizes: tuple[int, ...] = (75, 77)
    panels: tuple[str, ...] = ("oled", "miniled")
    min_hz: int = 100
    require_vrr: bool = False
    require_hdmi21: bool = False

    # ---------------- title tests ----------------
    def has_size(self, norm_title: str) -> bool:
        """The title names one of the wanted sizes."""
        return bool(_size_res(self.sizes)[0].search(norm_title))

    def names_other_size(self, norm_title: str) -> bool:
        """The title names a size that is not wanted, so it is a different variant."""
        return bool(_size_res(self.sizes)[1].search(norm_title))

    def panel_ok(self, norm_title: str) -> bool:
        """The title names a wanted panel family (always true when no family is required)."""
        pat = _panel_re(self.panels)
        return True if pat is None else bool(pat.search(norm_title))

    # ---------------- spec tests ----------------
    def spec_problems(self, hz: Optional[int], vrr: Optional[bool], hdmi21: Optional[bool]) -> list[str]:
        """Why these specs fall short of the floor; empty when they qualify."""
        out: list[str] = []
        if not hz or hz < self.min_hz:
            out.append(f"{hz if hz else 'unknown'} Hz panel, floor is {self.min_hz} Hz")
        if self.require_vrr and not vrr:
            out.append("no VRR")
        if self.require_hdmi21 and not hdmi21:
            out.append("no HDMI 2.1 input")
        return out

    def specs_qualify(self, hz: Optional[int], vrr: Optional[bool], hdmi21: Optional[bool]) -> bool:
        return not self.spec_problems(hz, vrr, hdmi21)

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
    def spec_label(self) -> str:
        bits = [f"native {self.min_hz} Hz or more"]
        if self.require_vrr:
            bits.append("VRR")
        if self.require_hdmi21:
            bits.append("HDMI 2.1")
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
        """Search terms for the shops that answer queries instead of listing a category."""
        out: list[str] = []
        for size in sorted(set(self.sizes)):
            for term in self.panel_terms():
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
        require_vrr=bool(d.get("require_vrr", defaults.require_vrr)),
        require_hdmi21=bool(d.get("require_hdmi21", defaults.require_hdmi21)),
    )


def active() -> Criteria:
    """The criteria in the saved config. Build once per run and pass it down; this reads the file."""
    return from_config(config_mod.load())
