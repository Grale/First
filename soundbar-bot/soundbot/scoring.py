"""Ranking: a fit score (how well the specs match what the buyer wants), a review score (critics + owners)
and an overall score. Every component is visible so a rank can be explained.

Two fit profiles, chosen in config "scoring" -> "profile":

cinema (default) - immersion first, 0-100
  height        4+ height channels 24 · 3 channels 20 · 2 channels 15 · fewer 0
                (dedicated height drivers earn the same as up-firing; virtual earns nothing)
  surround      wireless rears in the box 20 · wireless rears available 9 · none 0
  bass          wireless subwoofer in the box with an 8" driver or larger 14 · any wireless sub in the
                box 12 · bass built into the bar 7 · wireless sub available 6 · none 0
  channels      11+ main channels 10 · 9 ch 8 · 7 ch 6 · 5 ch 4 · 3 ch 2
  formats       Dolby Atmos + DTS:X 6 · Atmos only 4
  connections   eARC 4 · plus 2 for an HDMI input that passes 4K through to the TV
  calibration   room calibration or automatic EQ 4
  year          2026 8 · 2025 6 · 2024 4 · older 2
  priority      +8 for the models the buyer named

music - the same system judged as a stereo speaker, 0-100
  Drops the height and surround weighting to a third and spends it on measured tonal accuracy,
  streaming support (AirPlay 2 / Chromecast / Spotify Connect) and a line or phono input.

Both profiles then apply the deductions in tools/reviews/_fit_penalties.json, where a review found a
clash with the criteria (height effects that reviewers could not place, a sub that cannot keep up with
the bar, HDMI passthrough capped below the TV's own panel).

review (0-100): review_score (0-10) x 10, from tools/reviews research.
overall: weighted mean of fit and review (weights in config "scoring"); a model without reviews uses fit
only and is flagged. value: overall per 1000 EUR of the cheapest in-stock price (higher is better).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .criteria import PHYSICAL_HEIGHT
from .watchlist import Model

DEFAULT_PROFILE = "cinema"


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


def height_points(m: Model, four: int, three: int, two: int) -> int:
    """Height channels only count when they come from drivers rather than from a processor."""
    s = m.specs
    if s.height_type not in PHYSICAL_HEIGHT:
        return 0
    return _band(s.height_channels, [(4, four), (3, three), (2, two)], 0)


def surround_points(m: Model, included: int, optional: int) -> int:
    return {"wireless_included": included, "wireless_optional": optional}.get(m.specs.rears, 0)


def bass_points(m: Model, big: int, included: int, built_in: int, optional: int) -> int:
    sub = m.specs.subwoofer
    if sub == "wireless_included":
        driver = ((m.review or {}).get("specs_extra") or {}).get("sub_driver_in")
        return big if (driver and float(driver) >= 8) else included
    return {"built_in": built_in, "wireless_optional": optional}.get(sub, 0)


def _format_points(m: Model, both: int, atmos_only: int) -> int:
    if not m.specs.atmos:
        return 0
    return both if m.specs.dtsx else atmos_only


def fit_score(m: Model, profile: str = DEFAULT_PROFILE) -> tuple[float, dict]:
    extra = (m.review or {}).get("specs_extra") or {}
    s = m.specs

    if profile == "music":
        parts = {
            "height": height_points(m, 8, 7, 5),
            "surround": surround_points(m, 7, 3),
            "bass": bass_points(m, 12, 10, 6, 5),
            "channels": _band(s.channels, [(11, 6), (9, 5), (7, 4), (5, 3), (3, 2)], 0),
            "tonal": _band(extra.get("music_score"), [(9, 20), (8, 16), (7, 12), (6, 8)], 10),
            "streaming": min(12, 4 * len(extra.get("streaming") or [])),
            "analogue_in": 6 if extra.get("analogue_in") else 0,
            "formats": _format_points(m, 5, 4),
            "connections": (4 if s.earc else 0) + (2 if (s.hdmi_in or 0) >= 1 else 0),
            "year": _band(m.year, [(2026, 8), (2025, 6), (2024, 4)], 2) if m.year else 2,
            "priority": 8 if m.priority else 0,
        }
    else:
        parts = {
            "height": height_points(m, 24, 20, 15),
            "surround": surround_points(m, 20, 9),
            "bass": bass_points(m, 14, 12, 7, 6),
            "channels": _band(s.channels, [(11, 10), (9, 8), (7, 6), (5, 4), (3, 2)], 0),
            "formats": _format_points(m, 6, 4),
            "connections": (4 if s.earc else 0) + (2 if (s.hdmi_in or 0) >= 1 else 0),
            "calibration": 4 if extra.get("room_calibration") else 0,
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
