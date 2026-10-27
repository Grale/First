"""Ranking: a fit score (how well the specs match what the buyer wants), a review score (critics + owners)
and an overall score. Every component is visible so a rank can be explained.

Two fit profiles, chosen in config "scoring" -> "profile". Each is worth 92 points plus an 8-point bonus
for the models the buyer named, so a perfect model scores 100.

work (default) - a monitor to work at, 0-100
  panel         IPS Black 13 · Nano/Fast IPS 12 · Mini LED 12 · plain IPS 11 · WOLED 9 · QD-OLED 7 · VA 6
  density       pixels per inch: 140+ 11 · 120+ 9 · 105+ 8 · 95+ 5 · below 3 · unknown 5
  usb_c         power delivery: 90 W+ 12 · 65 W+ 9 · 45 W+ 6 · any 3 · none 0 · unknown 2
  kvm           built-in KVM 7 · none 0 · unknown 1
  eye_comfort   TUV Rheinland Eye Comfort: 5 stars 11 · 4 stars 8 · 3 stars 6 · certified, stars
                unstated 4 · nothing documented 0 · unknown 2
  contrast      OLED 7 (per-pixel) · otherwise 3000:1+ 7 · 2000+ 6 · 1500+ 4 · 1000+ 3 · unknown 3
  gamut         DCI-P3 95%+ 5 · 90%+ 4 · sRGB 99%+ 3 · unknown 2
  stand         height-adjustable 5 · fixed 0 · unknown 2
  hdr           True Black 400+ 5 · DisplayHDR 600+ 5 · 500 4 · 400 2 · HDR10 only 1 · unknown 1
  refresh       165 Hz+ 4 · 144 Hz 3 · 120 Hz 2 · 100 Hz 1
  year          2026 5 · 2025 4 · 2024 3 · older 2
  curvature     1500-1900R 2 · flat 2 · 800-1000R 1 · unknown 1
  dp            DisplayPort 2.1 1 · 1.4 1 · older 0
  response      measured GtG <=5 ms 1 · slower 0 · unknown 1
  burn_in       non-OLED 3 (nothing to insure) · OLED with 3+ year cover 3 · 2 years 2 · none 0

gaming - the gaming-first weighting, kept so a second profile stays available, 0-100
  refresh       240 Hz+ 18 · 165 Hz 14 · 144 Hz 11 · 120 Hz 8 · 100 Hz 5
  response      measured GtG <=1 ms 14 · <=3 ms 12 · <=5 ms 8 · <=8 ms 4 · slower 2 · unknown 5
  panel         QD-OLED 14 · WOLED 13 · Mini LED 11 · Nano/Fast IPS 10 · plain IPS 9 · VA 6
  contrast      OLED 10 · 3000:1+ 7 · 2000+ 6 · 1500+ 4 · 1000+ 3 · unknown 3
  vrr           G-Sync and FreeSync certified 7 · one of them 5 · VRR only 3 · none 0 · unknown 1
  hdr           True Black 400+ 7 · DisplayHDR 1000 7 · 600 5 · 500 4 · 400 2 · HDR10 only 1
  curvature     800R 5 · 1000R 4 · 1500-1900R 3 · flat 2 · unknown 2
  density       140+ 4 · 120+ 3 · 105+ 3 · 95+ 2 · below 1 · unknown 2
  year          2026 4 · 2025 3 · 2024 2 · older 1
  dp            DisplayPort 2.1 3 · 1.4 2 · older 1
  usb_c         90 W+ 2 · any 1 · none 0
  stand         height-adjustable 2 · unknown 1
  kvm           1 when present
  eye_comfort   1 for a documented certification

Three deliberate choices in the work profile, because they are the opposite of what a gaming score does:

* OLED ranks *below* IPS. QD-OLED's triangular subpixel layout fringes text and WOLED's RWBG layout
  does so differently; both carry burn-in risk against a static desktop. For a monitor that shows the
  same toolbars eight hours a day that is a cost, not a feature, however good the contrast is.
* A quoted response time can never earn the top band. Where a lab measured the panel, the measurement
  is used; where only the maker's "1 ms GtG" exists, the points are capped at the honest middle band.
  The gap between claim and measurement is the point.
* DisplayHDR 400 scores near nothing. It certifies 400 nits and no local dimming, which is roughly what
  an uncertified panel does anyway. True Black 400 (OLED) is a different and much stronger standard.

Both profiles then apply the deductions in tools/reviews/_fit_penalties.json, where a review found a
clash with the criteria (text fringing, a dishonest response claim, a coating that veils contrast, poor
uniformity, a stand that wobbles, scaling trouble).

review (0-100): review_score (0-10) x 10, from tools/reviews research.
overall: weighted mean of fit and review (weights in config "scoring"); a model without reviews uses fit
only and is flagged. value: overall per 1000 EUR of the cheapest in-stock price (higher is better).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .watchlist import Model

DEFAULT_PROFILE = "work"
PROFILES = ("work", "gaming")


@dataclass
class Score:
    fit: float
    review: Optional[float]
    overall: float
    parts: dict = field(default_factory=dict)
    confidence: str = ""
    has_review: bool = False
    value: Optional[float] = None


def _band(v: Optional[float], bands: list[tuple[float, int]], unknown: int) -> int:
    """Points for the first band whose threshold v reaches, counting down."""
    if v is None:
        return unknown
    for threshold, pts in bands:
        if v >= threshold:
            return pts
    return 0


def _band_lower_is_better(v: Optional[float], bands: list[tuple[float, int]], unknown: int,
                          worst: int) -> int:
    if v is None:
        return unknown
    for threshold, pts in bands:
        if v <= threshold:
            return pts
    return worst


def is_oled(m: Model) -> bool:
    return "OLED" in f"{m.panel} {m.family} {m.model_key}".upper()


def panel_points(text: str, ips_black: int, nano_ips: int, miniled: int, ips: int,
                 woled: int, qd_oled: int, va: int, other: int) -> int:
    """Points for the panel family named in the watchlist entry.

    Order matters: "Mini LED IPS" must read as Mini LED, and "QD-OLED" must not read as plain OLED.
    """
    t = (text or "").upper().replace("-", " ")
    if "MINI LED" in t or "MINILED" in t:
        return miniled
    if "OLED" in t:
        if "QD" in t or "QUANTUM" in t:
            return qd_oled
        if "WOLED" in t or "W OLED" in t or "LG DISPLAY" in t:
            return woled
        return woled
    if "IPS BLACK" in t:
        return ips_black
    if "NANO IPS" in t or "FAST IPS" in t:
        return nano_ips
    if "IPS" in t:
        return ips
    if "VA" in t:
        return va
    return other


def _ppi_points(m: Model, bands: list[tuple[float, int]], unknown: int) -> int:
    return _band(m.ppi, bands, unknown)


def _response_points(m: Model, bands: list[tuple[float, int]], unknown: int, worst: int,
                     quoted_cap: int) -> int:
    """Response-time points, measured where a lab measured it.

    A quoted figure is capped at `quoted_cap`: "1 ms GtG" is a marketing number almost everywhere, and
    a panel that has never been measured cannot earn the band reserved for ones that have.
    """
    extra = (m.review or {}).get("specs_extra") or {}
    measured = extra.get("measured_response_ms")
    if measured is not None:
        return _band_lower_is_better(float(measured), bands, unknown, worst)
    if m.specs.response_ms is not None:
        return min(quoted_cap, _band_lower_is_better(float(m.specs.response_ms), bands, unknown, worst))
    return unknown


def _contrast_points(m: Model, oled_pts: int, bands: list[tuple[float, int]], unknown: int) -> int:
    if is_oled(m):
        return oled_pts
    extra = (m.review or {}).get("specs_extra") or {}
    value = extra.get("measured_contrast")
    if value is None:
        value = m.specs.contrast
    return _band(None if value is None else float(value), bands, unknown)


def _gamut_points(m: Model, p3_95: int, p3_90: int, srgb_99: int, unknown: int) -> int:
    extra = (m.review or {}).get("specs_extra") or {}
    p3 = extra.get("measured_dci_p3_pct")
    if p3 is None:
        p3 = m.specs.dci_p3_pct
    if p3 is not None:
        if p3 >= 95:
            return p3_95
        if p3 >= 90:
            return p3_90
    if m.specs.srgb_pct is not None and m.specs.srgb_pct >= 99:
        return srgb_99
    return unknown if (p3 is None and m.specs.srgb_pct is None) else 0


def hdr_points(hdr: str, true_black: int, dhdr_1000: int, dhdr_600: int, dhdr_500: int,
               dhdr_400: int, hdr10: int, unknown: int) -> int:
    """Points for the HDR certification tier.

    DisplayHDR 400 is scored near zero on purpose: it asks for 400 nits, 95% sRGB and no local dimming
    at all, which an uncertified panel of the same class generally also does. "True Black 400" is the
    OLED tier and means something quite different.
    """
    t = (hdr or "").upper().replace("-", " ")
    if not t:
        return unknown
    if "TRUE BLACK" in t:
        return true_black
    for marker, pts in (("1400", dhdr_1000), ("1000", dhdr_1000), ("600", dhdr_600),
                        ("500", dhdr_500), ("400", dhdr_400)):
        if marker in t:
            return pts
    return hdr10


def eye_comfort_points(stars: Optional[int], five: int, four: int, three: int, certified: int,
                       none_documented: int, unknown: int) -> int:
    """Points for a TUV Rheinland Eye Comfort rating.

    The star scale is young and thinly documented, so the bands distinguish "verified at five stars"
    from "certified, stars not stated" from "nothing found" from "not looked into". A model that simply
    has not been checked lands on `unknown`, which is deliberately neutral rather than zero.
    """
    if stars is None:
        return unknown
    if stars >= 5:
        return five
    if stars == 4:
        return four
    if stars == 3:
        return three
    if stars >= 1:
        return certified
    return none_documented


def curvature_points(curvature: str, aggressive: int, medium: int, gentle: int, flat: int,
                     unknown: int) -> int:
    """Points by curve radius. A smaller R is a tighter curve: 800R wraps, 1900R is nearly flat."""
    t = (curvature or "").upper().strip()
    if not t:
        return unknown
    if "FLAT" in t:
        return flat
    digits = "".join(c for c in t if c.isdigit())
    if not digits:
        return unknown
    r = int(digits)
    if r <= 1000:
        return aggressive
    if r <= 1200:
        return medium
    return gentle


def dp_points(version: str, v21: int, v14: int, older: int, unknown: int) -> int:
    t = (version or "").strip()
    if not t:
        return unknown
    try:
        v = float(t.split()[0])
    except ValueError:
        return unknown
    if v >= 2.0:
        return v21
    if v >= 1.4:
        return v14
    return older


def vrr_points(m: Model, both: int, one: int, plain: int, none: int, unknown: int) -> int:
    brand = (m.specs.vrr_brand or "").upper()
    has_gsync = "G SYNC" in brand.replace("-", " ") or "GSYNC" in brand
    has_freesync = "FREESYNC" in brand
    if has_gsync and has_freesync:
        return both
    if has_gsync or has_freesync:
        return one
    if m.specs.vrr is True:
        return plain
    if m.specs.vrr is False:
        return none
    return unknown


def burn_in_points(m: Model, covered_long: int, covered_short: int, uncovered: int,
                   not_oled: int) -> int:
    """OLED burn-in cover. A non-OLED scores `not_oled`: there is no risk to insure against."""
    if not is_oled(m):
        return not_oled
    years = m.specs.burn_in_warranty_years
    if years is None:
        return uncovered
    if years >= 3:
        return covered_long
    if years >= 2:
        return covered_short
    return uncovered


def fit_score(m: Model, profile: str = DEFAULT_PROFILE) -> tuple[float, dict]:
    s = m.specs

    if profile == "gaming":
        parts = {
            "refresh": _band(s.hz, [(240, 18), (165, 14), (144, 11), (120, 8), (100, 5)], 0),
            "response": _response_points(m, [(1, 14), (3, 12), (5, 8), (8, 4)], unknown=5, worst=2,
                                         quoted_cap=8),
            "panel": panel_points(m.panel, ips_black=9, nano_ips=10, miniled=11, ips=9,
                                  woled=13, qd_oled=14, va=6, other=7),
            "contrast": _contrast_points(m, 10, [(3000, 7), (2000, 6), (1500, 4), (1000, 3)], 3),
            "vrr": vrr_points(m, both=7, one=5, plain=3, none=0, unknown=1),
            "hdr": hdr_points(s.hdr, true_black=7, dhdr_1000=7, dhdr_600=5, dhdr_500=4,
                              dhdr_400=2, hdr10=1, unknown=1),
            "curvature": curvature_points(s.curvature, aggressive=5, medium=4, gentle=3, flat=2,
                                          unknown=2),
            "density": _ppi_points(m, [(140, 4), (120, 3), (105, 3), (95, 2)], 2),
            "year": _band(m.year, [(2026, 4), (2025, 3), (2024, 2)], 1) if m.year else 1,
            "dp": dp_points(s.dp_version, v21=3, v14=2, older=1, unknown=1),
            "usb_c": _band(s.usb_c_pd_w, [(90, 2), (1, 1)], 0),
            "stand": 2 if s.height_adjust else (1 if s.height_adjust is None else 0),
            "kvm": 1 if s.kvm else 0,
            "eye_comfort": 1 if (s.tuv_eye_comfort_stars or 0) >= 1 else 0,
            "priority": 8 if m.priority else 0,
        }
    else:
        parts = {
            "panel": panel_points(m.panel, ips_black=13, nano_ips=12, miniled=12, ips=11,
                                  woled=9, qd_oled=7, va=6, other=8),
            "density": _ppi_points(m, [(140, 11), (120, 9), (105, 8), (95, 5)], 5),
            "usb_c": _band(s.usb_c_pd_w, [(90, 12), (65, 9), (45, 6), (1, 3)],
                           2 if s.usb_c_pd_w is None else 0),
            "kvm": 7 if s.kvm else (1 if s.kvm is None else 0),
            "eye_comfort": eye_comfort_points(s.tuv_eye_comfort_stars, five=11, four=8, three=6,
                                              certified=4, none_documented=0, unknown=2),
            "contrast": _contrast_points(m, 7, [(3000, 7), (2000, 6), (1500, 4), (1000, 3)], 3),
            "gamut": _gamut_points(m, p3_95=5, p3_90=4, srgb_99=3, unknown=2),
            "stand": 5 if s.height_adjust else (2 if s.height_adjust is None else 0),
            "hdr": hdr_points(s.hdr, true_black=5, dhdr_1000=5, dhdr_600=5, dhdr_500=4,
                              dhdr_400=2, hdr10=1, unknown=1),
            "refresh": _band(s.hz, [(165, 4), (144, 3), (120, 2), (100, 1)], 0),
            "year": _band(m.year, [(2026, 5), (2025, 4), (2024, 3)], 2) if m.year else 2,
            "curvature": curvature_points(s.curvature, aggressive=1, medium=2, gentle=2, flat=2,
                                          unknown=1),
            "dp": dp_points(s.dp_version, v21=1, v14=1, older=0, unknown=1),
            "response": _response_points(m, [(5, 1)], unknown=1, worst=0, quoted_cap=1),
            "burn_in": burn_in_points(m, covered_long=3, covered_short=2, uncovered=0, not_oled=3),
            "priority": 8 if m.priority else 0,
        }

    # Deductions. A penalty may name the profiles it applies to: QD-OLED text fringing is a real cost
    # to someone reading code all day and no cost at all to someone playing a game, so it would be
    # wrong to charge it in both. A penalty with no "profiles" key applies everywhere.
    penalties = [p for p in ((m.review or {}).get("fit_penalties") or [])
                 if not p.get("profiles") or profile in p["profiles"]]
    if penalties:
        parts["penalties"] = sum(int(p.get("points", 0)) for p in penalties)
    return float(max(0, sum(parts.values()))), parts


def score_model(m: Model, cfg: dict, best_price: Optional[float] = None) -> Score:
    weights = cfg.get("scoring", {})
    w_fit = float(weights.get("fit_weight", 0.5))
    w_rev = float(weights.get("review_weight", 0.5))
    fit, parts = fit_score(m, str(weights.get("profile", DEFAULT_PROFILE)).lower())
    rev = (m.review or {}).get("review_score") if (m.review or {}).get("critic") is not None else None
    review = float(rev) * 10 if rev is not None else None
    if review is None or (w_fit + w_rev) == 0:
        overall = fit
    else:
        overall = (fit * w_fit + review * w_rev) / (w_fit + w_rev)
    value = (overall / (best_price / 1000.0)) if best_price else None
    return Score(fit=round(fit, 1), review=None if review is None else round(review, 1), overall=round(overall, 1),
                 parts=parts, confidence=(m.review or {}).get("confidence", ""), has_review=review is not None,
                 value=None if value is None else round(value, 1))


def rank_models(models: list[Model], cfg: dict, best_prices: dict[str, float]) -> list[tuple[int, Model, Score]]:
    scored = [(m, score_model(m, cfg, best_prices.get(m.model_key))) for m in models]
    scored.sort(key=lambda t: (-t[1].overall, -(t[1].review or 0), t[0].model_key))
    return [(i + 1, m, s) for i, (m, s) in enumerate(scored)]
