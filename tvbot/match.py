"""Match shop product titles to watchlist models.

Rules:
- Title and aliases are normalised to upper-case alphanumerics separated by single spaces.
- An alias matches when it appears in the title either as whole words or embedded in a longer
  code with no spaces (so "QN85D" matches "QE75QN85DATXXH", "C5" matches "OLED77C54LA").
- The title (or the alias) must carry one of the wanted size markers, and accessories are rejected.
- When several models match, the longest matching alias wins. Rejected models take part as
  negatives, so "TCL 75C6KS" is claimed by the rejected 75C6KS rather than by 75C6K.

Which sizes and panel families count comes from tvbot.criteria, not from this module.
"""
from __future__ import annotations
import re
from typing import Iterable, Optional

from .criteria import Criteria
from .watchlist import Model, Rejected

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_ACCESSORY = ("SOUNDBAR", "SOUND BAR", "REMOTE", "ΤΗΛΕΧΕΙΡΙΣΤΗΡΙΟ", "BRACKET", "ΒΑΣΗ ", "WALL MOUNT",
              "ΒΑΣΗ ΤΟΙΧΟΥ", "STAND", "CABLE", "ΚΑΛΩΔΙΟ", "ΚΑΘΑΡΙΣΤΗΣ", "PURIFIER", "PHONE", "SMARTPHONE",
              "TABLET", "MONITOR", "ΟΘΟΝΗ Η/Υ", "PROJECTOR")


def normalize(text: str) -> str:
    t = (text or "").upper()
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
    up = (title or "").upper()
    return any(k in up for k in _ACCESSORY)


def match_aliases(title: str, aliases: Iterable[str], crit: Criteria) -> Optional[str]:
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
    # size gate: the alias itself may carry the size (OLED77C5) or the title must
    if not crit.has_size(normalize(best)) and not crit.has_size(norm):
        return None
    # a title that names another size and never a wanted one is a different variant
    if not crit.has_size(norm) and crit.names_other_size(norm):
        return None
    return best


def match_model(title: str, model: Model, crit: Criteria) -> Optional[str]:
    return match_aliases(title, model.all_aliases(), crit)


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
    """Loose filter used by the discovery scan: wanted size and a wanted panel family in the title."""
    if is_accessory(title):
        return False
    norm = normalize(title)
    return crit.has_size(norm) and crit.panel_ok(norm)
