"""Ranking: a fit score (how well the specs match what the buyer wants), a review score (critics + owners)
and an overall score. Every component is visible so a rank can be explained.

Two fit profiles, chosen in config "scoring" -> "profile":

picture (default) - picture quality first, 0-100
  panel         QD-OLED / META OLED 22 · OLED 20 · RGB Mini LED 17 · QD or Neo QLED Mini LED 13 ·
                plain Mini LED 10 · anything else 5
  contrast      OLED 20 (per-pixel, no blooming) · otherwise measured dimming zones
                1500+ 18 · 1000+ 15 · 500+ 11 · 300+ 8 · unknown 6
  peak nits     2500+ 22 · 2000+ 19 · 1500+ 15 · 1000+ 11 · 600+ 6 · unknown 8
  refresh       165 Hz+ 10 · 144 Hz 9 · 120 Hz 8 · 100 Hz 6
  hdmi21        4+ ports 6 · 3 ports 5 · 2 ports 4 · 1 port 2
  input lag     <=6 ms 4 · <=10 ms 3 · <=15 ms 2 · unknown 2
  model year    2026 8 · 2025 6 · 2024 4 · older 2
  priority      +8 for the models the buyer named

gaming - the gaming-first profile, 0-100
  refresh       120 Hz 12 · 144 Hz 16 · 165 Hz+ 20
  hdmi21        1 port 4 · 2 ports 10 · 3 ports 13 · 4+ ports 16
  panel         OLED 12 · RGB Mini LED 12 · quantum-dot Mini LED 9 · plain Mini LED 6
  dimming zones 1500+ 14 · 1000+ 11 · 500+ 8 · 300+ 5 · unknown 4 (OLED scores full marks)
  peak nits     2500+ 14 · 1500+ 11 · 1000+ 8 · 600+ 5 · unknown 4
  input lag     <=6 ms 8 · <=10 ms 6 · <=15 ms 4 · unknown 3
  model year    2026 8 · 2025 6 · 2024 4 · older 2
  priority      +8 for the models the buyer named

Both profiles then apply the deductions in tools/reviews/_fit_penalties.json, where a review found a clash
with the criteria (edge-lit despite a Mini LED label, no local dimming, dimming off with VRR, high lag).

review (0-100): review_score (0-10) x 10, from tools/reviews research.
overall: weighted mean of fit and review (weights in config "scoring"); a model without reviews uses fit only
and is flagged. value: overall per 1000 EUR of the cheapest in-stock price (higher is better).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .watchlist import Model

DEFAULT_PROFILE = "picture"


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
    if v is None:
        return unknown
    for threshold, pts in bands:
        if v >= threshold:
            return pts
    return 0


def _lag_points(ms: Optional[float], bands: list[tuple[float, int]], unknown: int, worst: int) -> int:
    if ms is None:
        return unknown
    for threshold, pts in bands:
        if ms <= threshold:
            return pts
    return worst


def is_oled(m: Model) -> bool:
    return "OLED" in f"{m.backlight} {m.family} {m.model_key}".upper()


def backlight_points(text: str, oled: int = 12, rgb: int = 12, quantum: int = 9,
                     mini: int = 6, other: int = 6) -> int:
    """Points for the panel/backlight type named in the watchlist entry."""
    t = (text or "").upper()
    if "OLED" in t:
        return oled
    if "RGB" in t:
        return rgb
    if any(k in t for k in ("QD", "SQD", "NEO QLED", "QUANTUM", "NEO")):
        return quantum
    if "MINI" in t:
        return mini
    return other


def _panel_points_picture(m: Model) -> int:
    t = f"{m.backlight} {m.family}".upper()
    if "OLED" in t:
        # QD-OLED (Samsung/Sony) and LG's META panels are brighter and more saturated than plain W-OLED
        return 22 if any(k in t for k in ("QD OLED", "QD-OLED", "QDOLED", "META", "EVO")) else 20
    return backlight_points(t, oled=20, rgb=17, quantum=13, mini=10, other=5)


def fit_score(m: Model, profile: str = DEFAULT_PROFILE) -> tuple[float, dict]:
    extra = (m.review or {}).get("specs_extra") or {}
    zones, nits, lag = extra.get("dimming_zones"), extra.get("peak_nits"), extra.get("input_lag_ms")
    oled = is_oled(m)

    if profile == "gaming":
        parts = {
            "refresh": _band(m.specs.hz, [(165, 20), (144, 16), (120, 12)], 0),
            "hdmi21": _band(m.specs.hdmi21_ports, [(4, 16), (3, 13), (2, 10), (1, 4)], 10 if m.specs.hdmi21 else 0),
            "panel": backlight_points(m.backlight, oled=12, rgb=12, quantum=9, mini=6, other=6),
            # an OLED controls light per pixel, so it earns the full dimming band
            "zones": 14 if oled else _band(zones, [(1500, 14), (1000, 11), (500, 8), (300, 5)], 4),
            "nits": _band(nits, [(2500, 14), (1500, 11), (1000, 8), (600, 5)], 4),
            "input_lag": _lag_points(lag, [(6, 8), (10, 6), (15, 4)], unknown=3, worst=3),
            "year": _band(m.year, [(2026, 8), (2025, 6), (2024, 4)], 2) if m.year else 2,
            "priority": 8 if m.priority else 0,
        }
    else:
        parts = {
            "panel": _panel_points_picture(m),
            "contrast": 20 if oled else _band(zones, [(1500, 18), (1000, 15), (500, 11), (300, 8)], 6),
            "nits": _band(nits, [(2500, 22), (2000, 19), (1500, 15), (1000, 11), (600, 6)], 8),
            "refresh": _band(m.specs.hz, [(165, 10), (144, 9), (120, 8), (100, 6)], 0),
            "hdmi21": _band(m.specs.hdmi21_ports, [(4, 6), (3, 5), (2, 4), (1, 2)], 4 if m.specs.hdmi21 else 0),
            "input_lag": _lag_points(lag, [(6, 4), (10, 3), (15, 2)], unknown=2, worst=1),
            "year": _band(m.year, [(2026, 8), (2025, 6), (2024, 4)], 2) if m.year else 2,
            "priority": 8 if m.priority else 0,
        }

    penalties = (m.review or {}).get("fit_penalties") or []
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
