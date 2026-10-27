from __future__ import annotations
import json
import threading
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Any, Optional

from .paths import WATCHLIST_PATH

if TYPE_CHECKING:
    from .criteria import Criteria

_lock = threading.Lock()


@dataclass
class Specs:
    """Spec-sheet facts about a monitor, as the maker publishes them.

    Only claims go here. Measured figures - what a lab actually got for response time, brightness,
    contrast or gamut - live in the review entry under `specs_extra`, because the gap between the two
    is the whole point: a panel quoted at 1 ms GtG that measures 8 ms should not score as if it were fast.
    """
    hz: Optional[int] = None
    width: Optional[int] = None                 # native horizontal pixels
    height: Optional[int] = None                # native vertical pixels
    response_ms: Optional[float] = None         # quoted GtG
    usb_c_pd_w: Optional[int] = None            # USB-C / Thunderbolt power delivery in watts
    kvm: Optional[bool] = None
    height_adjust: Optional[bool] = None
    curvature: str = ""                         # "800R", "1800R", "1900R", "flat"
    dp_version: str = ""                        # "1.2", "1.4", "2.1"
    hdr: str = ""                               # "DisplayHDR 400", "DisplayHDR True Black 400", ...
    srgb_pct: Optional[int] = None
    dci_p3_pct: Optional[int] = None
    contrast: Optional[int] = None              # static contrast ratio; None for OLED (per-pixel)
    tuv_eye_comfort_stars: Optional[int] = None  # TUV Rheinland Eye Comfort stars; 0 = none documented
    vrr: Optional[bool] = None
    vrr_brand: str = ""                         # "G-Sync Compatible", "FreeSync Premium Pro", ...
    burn_in_warranty_years: Optional[int] = None  # OLED only


@dataclass
class Model:
    brand: str
    model_key: str
    family: str = ""
    year: Optional[int] = None
    panel: str = ""                 # "QD-OLED", "WOLED", "Nano IPS", "IPS Black", "Mini LED VA", "VA"
    size_inch: Optional[float] = None
    specs: Specs = field(default_factory=Specs)
    source_url: str = ""
    aliases: list[str] = field(default_factory=list)
    priority: bool = False
    notes: str = ""
    enabled: bool = True
    review: dict = field(default_factory=dict)   # critic/user review evidence, see tools/reviews

    def meets(self, crit: "Criteria") -> bool:
        """True when the specs clear the floor in the active criteria."""
        s = self.specs
        return crit.specs_qualify(s.hz, s.width, s.height, s.height_adjust, s.usb_c_pd_w,
                                  s.kvm, s.vrr, self.panel)

    @property
    def resolution_label(self) -> str:
        s = self.specs
        return f"{s.width}×{s.height}" if s.width and s.height else "?"

    @property
    def ppi(self) -> Optional[float]:
        """Pixel density. Text sharpness at a desk is a function of this, not of resolution alone:
        3440x1440 is 109 PPI at 34 inches and only 96 PPI at 38."""
        s = self.specs
        if not (s.width and s.height and self.size_inch):
            return None
        return round(((s.width ** 2 + s.height ** 2) ** 0.5) / float(self.size_inch), 1)

    @property
    def display_name(self) -> str:
        fam = ""
        if self.family and self.family.upper() not in self.model_key.upper():
            fam = f" ({self.family})"
        return f"{self.brand} {self.model_key}{fam}".strip()

    def all_aliases(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for a in [self.model_key, *self.aliases]:
            a = (a or "").strip()
            if a and a.upper() not in seen:
                seen.add(a.upper())
                out.append(a)
        return out

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Rejected:
    brand: str
    model_key: str
    reason: str
    source_url: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class Watchlist:
    models: list[Model] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)

    def active(self) -> list[Model]:
        return [m for m in self.models if m.enabled]

    def watched(self, crit: "Criteria") -> list[Model]:
        return [m for m in self.active() if m.meets(crit)]

    def get(self, model_key: str) -> Optional[Model]:
        for m in self.models:
            if m.model_key.upper() == model_key.upper():
                return m
        return None

    def validate(self, crit: "Criteria") -> list[str]:
        problems: list[str] = []
        keys: set[str] = set()
        for m in self.models:
            if m.model_key.upper() in keys:
                problems.append(f"duplicate model_key {m.model_key}")
            keys.add(m.model_key.upper())
            if not m.source_url:
                problems.append(f"{m.model_key}: missing source_url")
            s = m.specs
            for why in crit.spec_problems(s.hz, s.width, s.height, s.height_adjust,
                                          s.usb_c_pd_w, s.kvm, s.vrr, m.panel):
                problems.append(f"{m.model_key}: {why}")
        return problems


def _int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _bool(v: Any) -> Optional[bool]:
    return None if v is None else bool(v)


def specs_from_dict(d: dict[str, Any]) -> Specs:
    return Specs(
        hz=_int(d.get("hz")),
        width=_int(d.get("width")),
        height=_int(d.get("height")),
        response_ms=_float(d.get("response_ms")),
        usb_c_pd_w=_int(d.get("usb_c_pd_w")),
        kvm=_bool(d.get("kvm")),
        height_adjust=_bool(d.get("height_adjust")),
        curvature=d.get("curvature", "") or "",
        dp_version=str(d.get("dp_version", "") or ""),
        hdr=d.get("hdr", "") or "",
        srgb_pct=_int(d.get("srgb_pct")),
        dci_p3_pct=_int(d.get("dci_p3_pct")),
        contrast=_int(d.get("contrast")),
        tuv_eye_comfort_stars=_int(d.get("tuv_eye_comfort_stars")),
        vrr=_bool(d.get("vrr")),
        vrr_brand=d.get("vrr_brand", "") or "",
        burn_in_warranty_years=_int(d.get("burn_in_warranty_years")),
    )


def model_from_dict(d: dict[str, Any]) -> Model:
    return Model(
        brand=d.get("brand", ""),
        model_key=d.get("model_key", ""),
        family=d.get("family", "") or "",
        year=_int(d.get("year")),
        panel=d.get("panel", "") or "",
        size_inch=_float(d.get("size_inch")),
        specs=specs_from_dict(d.get("specs") or {}),
        source_url=d.get("source_url", "") or "",
        aliases=list(d.get("aliases") or []),
        priority=bool(d.get("priority", False)),
        notes=d.get("notes", "") or "",
        enabled=bool(d.get("enabled", True)),
        review=dict(d.get("review") or {}),
    )


def load() -> Watchlist:
    with _lock:
        if not WATCHLIST_PATH.exists():
            return Watchlist()
        data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    models = [model_from_dict(d) for d in data.get("models", [])]
    rejected = [Rejected(brand=r.get("brand", ""), model_key=r.get("model_key", ""), reason=r.get("reason", ""),
                         source_url=r.get("source_url", ""), aliases=list(r.get("aliases") or []))
                for r in data.get("rejected", [])]
    return Watchlist(models=models, rejected=rejected)


def save(wl: Watchlist) -> None:
    data = {"models": [m.to_dict() for m in wl.models], "rejected": [asdict(r) for r in wl.rejected]}
    with _lock:
        WATCHLIST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
