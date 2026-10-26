"""What counts as a soundbar worth watching: true Dolby Atmos, and no speaker cables.

Everything the buyer's requirements touch lives here and is driven by the config "criteria" block, so a
change of requirements is a settings edit rather than a hunt through the matcher, the engine and the shops.

    min_height_channels         lowest number of height channels that qualifies (the third number of a
                                layout like 11.1.4). Two is the floor for real overhead imaging: one
                                up-firing driver (5.1.1) cannot place a sound left or right of you.
    require_physical_height     height must come from drivers that fire at the ceiling or from dedicated
                                height drivers, never from a virtual processor. This is the difference
                                between "Dolby Atmos" on the box and Dolby Atmos in the room.
    require_earc                an HDMI eARC output is required. Plain ARC carries Atmos only inside
                                lossy Dolby Digital+, so a bar without eARC cannot pass the lossless
                                TrueHD Atmos track from a disc or from a TV app that sends it.
    no_wired_speakers           a system whose subwoofer or rear speakers connect with a speaker cable
                                does not qualify. This is the "wireless" requirement: components may be
                                in the box or sold separately, but they talk to the bar over the air.
    require_sub_included        stricter: the box must contain a wireless subwoofer.
    require_rears_included      stricter: the box must contain wireless rear speakers.
    min_channels                lowest number of main (ear-level) channels that qualifies.

The two "included" switches are off by default: a single-bar system such as the Sonos Arc Ultra or the
Sony Bar 9 has no wired speaker anywhere and earns its place on the list, it simply scores below a
Q990H-class four-piece set, which is what the fit score is for.
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from . import config as config_mod
from .models import Specs

# How a system's subwoofer or rear speakers connect. "wired" is the only value the wireless rule rejects.
CONNECTIONS = {
    "wireless_included": "wireless, in the box",
    "wireless_optional": "wireless, sold separately",
    "built_in": "built into the bar",
    "none": "not available",
    "wired": "speaker cable",
}
WIRELESS_OK = ("wireless_included", "wireless_optional", "built_in", "none")

# Where the height channels come from. Only the first two are Dolby Atmos in the room.
HEIGHT_TYPES = {
    "upfiring": "up-firing drivers",
    "dedicated": "dedicated height drivers",
    "virtual": "virtual (processing only)",
    "none": "none",
}
PHYSICAL_HEIGHT = ("upfiring", "dedicated")

# A channel layout as the shops print it: 11.1.4, 5.1.2, 7.0.2, 3.1, 2.0 …
_LAYOUT_RE = re.compile(r"(?<![0-9.])([0-9]{1,2})\.([0-9])(?:\.([0-9]))?(?![0-9.])")

# Words that say the listing is a soundbar rather than a speaker, a TV or an amplifier. Greek shops use
# their own word for it, and Sony's bars carry "Theatre Bar" in the product name instead. Written
# without accents because every title is folded before it is tested.
_BAR_WORDS = ("SOUNDBAR", "SOUND BAR", "SOUNDBARS", "ΣΟΥΝΤΜΠΑΡ", "ΗΧΟΜΠΑΡΑ", "ΜΠΑΡΑ ΗΧΟΥ",
              "ΜΠΑΡΑ ΗΧΟΥ ΤΗΛΕΟΡΑΣΗΣ", "THEATRE BAR", "THEATER BAR", "CINEMA BAR", "HOME CINEMA BAR")
# Listings that lead with one of these are a component sold on its own, even when the title also
# names a soundbar ("Subwoofer for Soundbar HARMAN KARDON Citation Sub").
_COMPONENT_LEAD = re.compile(
    r"^(SUBWOOFER|SUB\b|WIRELESS SUBWOOFER|REAR SPEAKER|REAR SPEAKERS|WIRELESS SURROUND|SURROUND SPEAKER|"
    r"SURROUND SPEAKERS|SPEAKER KIT|ΥΠΟΓΟΥΦΕΡ|ΗΧΕΙΑ SURROUND)")
# What follows one of these in a title is what comes in the box, not what the listing is selling.
_INCLUDES = re.compile(r"\s(?:ΜΕ|ΚΑΙ|WITH|AND|PLUS|INCL|INCLUDING)\s|[,+&]")
# Accessories that are never a soundbar, when the title leads with one of them.
_ACCESSORY = ("BRACKET", "WALL MOUNT", "ΒΑΣΗ ΤΟΙΧΟΥ", "ΒΑΣΗ ", "STAND FOR", "CABLE", "ΚΑΛΩΔΙΟ",
              "REMOTE", "ΤΗΛΕΧΕΙΡΙΣΤΗΡΙΟ", "PC SPEAKERS", "ΗΧΕΙΑ Η/Υ", "SOUNDBAR STAND", "COVER",
              "ΘΗΚΗ", "ADAPTER", "ΑΝΤΑΠΤΟΡΑΣ")

BRANDS = ("Samsung", "Sony", "LG", "JBL", "Sonos", "Bose", "Harman Kardon", "Marshall", "Klipsch",
          "Philips", "Hisense", "TCL", "Denon", "Sennheiser", "Bowers & Wilkins", "Panasonic", "Sharp")


def parse_layout(text: str) -> Optional[tuple[int, int, int]]:
    """'HW-Q990H 11.1.4 Channels' -> (11, 1, 4) ; 'Bar 8 5.0.2' -> (5, 0, 2) ; '3.1' -> (3, 1, 0)."""
    m = _LAYOUT_RE.search(text or "")
    if not m:
        return None
    main, sub, height = m.group(1), m.group(2), m.group(3)
    return int(main), int(sub), int(height or 0)


def fold(text: str) -> str:
    """Upper-case and drop accents, so 'Ηχομπάρα' and 'ΗΧΟΜΠΑΡΑ' read the same.

    Greek shops write the accented form and upper-casing keeps the accent (Ηχομπάρα -> ΗΧΟΜΠΆΡΑ), so a
    plain upper-case comparison misses every Greek title.
    """
    s = unicodedata.normalize("NFD", (text or "").upper())
    return "".join(c for c in s if not unicodedata.combining(c))


def is_component_or_accessory(title: str) -> bool:
    """A subwoofer, a rear-speaker kit, a bracket or a cable rather than a soundbar.

    This is the hard rejection: it holds whatever else the title says, and it is all that the matcher
    needs, because a model code in the title is its own proof that the listing is that soundbar.

    The accessory words are only looked for in the head of the title, before the first "with" or "and".
    Greek shops list what is in the box in the title itself - "Samsung HW-Q990F Soundbar 11.1.4 …
    με Ασύρματο Subwoofer και Τηλεχειριστήριο Μαύρο" is a soundbar that comes with a remote, not a
    remote - so a word found after one of those is a feature, not the thing being sold.
    """
    up = fold(title).strip()
    head = _INCLUDES.split(up, 1)[0] + " "
    if any(k in head for k in _ACCESSORY):
        return True
    return bool(_COMPONENT_LEAD.match(up))


def looks_like_soundbar(title: str) -> bool:
    """The title names a soundbar in so many words.

    Used by the discovery scan, which has no model code to go on and must not report every speaker in
    the shop. A listing that fails this can still be matched by a watchlist alias.
    """
    if is_component_or_accessory(title):
        return False
    up = fold(title)
    return any(w in up for w in _BAR_WORDS)


@dataclass(frozen=True)
class Criteria:
    min_height_channels: int = 2
    require_physical_height: bool = True
    require_earc: bool = True
    no_wired_speakers: bool = True
    require_sub_included: bool = False
    require_rears_included: bool = False
    min_channels: float = 3.0

    # ---------------- title tests ----------------
    def title_layout_ok(self, title: str) -> Optional[bool]:
        """True/False when the title prints a channel layout, None when it does not print one."""
        layout = parse_layout(title)
        if layout is None:
            return None
        main, _sub, height = layout
        return height >= self.min_height_channels and main >= self.min_channels

    def looks_like_candidate(self, title: str) -> bool:
        """Loose filter for the discovery scan: a soundbar whose title does not rule it out."""
        if not looks_like_soundbar(title):
            return False
        ok = self.title_layout_ok(title)
        if ok is not None:
            return ok
        # No layout printed: keep it only when the title claims Atmos, and let the research round decide.
        return "ATMOS" in (title or "").upper()

    # ---------------- spec tests ----------------
    def spec_problems(self, specs: Specs) -> list[str]:
        """Why these specs fall short; empty when they qualify."""
        out: list[str] = []
        h = specs.height_channels
        if h is None or h < self.min_height_channels:
            count = 'unknown' if h is None else h
            plural = '' if h == 1 else 's'
            out.append(f"{count} height channel{plural}, floor is {self.min_height_channels}")
        if self.require_physical_height and specs.height_type not in PHYSICAL_HEIGHT:
            out.append(f"height is {HEIGHT_TYPES.get(specs.height_type, specs.height_type or 'unknown')}, "
                       "not drivers that fire at the ceiling")
        if not specs.atmos:
            out.append("no Dolby Atmos decoding")
        if self.require_earc and not specs.earc:
            out.append("no HDMI eARC (cannot receive lossless TrueHD Atmos)")
        if specs.channels is not None and specs.channels < self.min_channels:
            out.append(f"{specs.channels:g} main channels, floor is {self.min_channels:g}")
        if self.no_wired_speakers:
            if specs.subwoofer == "wired":
                out.append("subwoofer connects with a speaker cable")
            if specs.rears == "wired":
                out.append("rear speakers connect with a speaker cable")
        if self.require_sub_included and specs.subwoofer != "wireless_included":
            out.append("no wireless subwoofer in the box")
        if self.require_rears_included and specs.rears != "wireless_included":
            out.append("no wireless rear speakers in the box")
        return out

    def specs_qualify(self, specs: Specs) -> bool:
        return not self.spec_problems(specs)

    # ---------------- labels and queries ----------------
    @property
    def atmos_label(self) -> str:
        bits = [f"{self.min_height_channels}+ height channels"]
        if self.require_physical_height:
            bits.append("from real up-firing drivers")
        if self.require_earc:
            bits.append("eARC")
        return ", ".join(bits)

    @property
    def wireless_label(self) -> str:
        if not self.no_wired_speakers:
            return "any connection"
        bits = ["no speaker cables"]
        if self.require_sub_included:
            bits.append("wireless sub in the box")
        if self.require_rears_included:
            bits.append("wireless rears in the box")
        return ", ".join(bits)

    @property
    def label(self) -> str:
        return f"true Dolby Atmos soundbars ({self.atmos_label}; {self.wireless_label})"

    @property
    def spec_label(self) -> str:
        return f"{self.min_channels:g}+ main channels, {self.atmos_label}"

    def discovery_queries(self, brands: tuple[str, ...] = BRANDS) -> list[str]:
        """Search terms for the shops that answer queries instead of listing a category."""
        out = ["soundbar Dolby Atmos", "soundbar wireless subwoofer"]
        out += [f"{b} soundbar" for b in brands]
        return out


def from_config(cfg: dict) -> Criteria:
    d = (cfg or {}).get("criteria") or {}
    defaults = Criteria()
    return Criteria(
        min_height_channels=int(d.get("min_height_channels", defaults.min_height_channels) or 0),
        require_physical_height=bool(d.get("require_physical_height", defaults.require_physical_height)),
        require_earc=bool(d.get("require_earc", defaults.require_earc)),
        no_wired_speakers=bool(d.get("no_wired_speakers", defaults.no_wired_speakers)),
        require_sub_included=bool(d.get("require_sub_included", defaults.require_sub_included)),
        require_rears_included=bool(d.get("require_rears_included", defaults.require_rears_included)),
        min_channels=float(d.get("min_channels", defaults.min_channels) or 0),
    )


def active() -> Criteria:
    """The criteria in the saved config. Build once per run and pass it down; this reads the file."""
    return from_config(config_mod.load())
