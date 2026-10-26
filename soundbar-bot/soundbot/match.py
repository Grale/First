"""Match shop product titles to watchlist models.

Rules:
- Title and aliases are normalised to upper-case alphanumerics separated by single spaces.
- An alias matches when it appears in the title as whole words, or - for aliases of five characters or
  more - embedded in a longer code with no spaces, so "Q990H" matches "HW-Q990H/EN" while a short alias
  such as "SC9S" has to stand on its own. Four characters embedded anywhere would let Sony's "Bar 8"
  claim a "JBL Bar 800".
- A generation marker has to agree: a title that says MK2 is only ever matched by a model whose own
  aliases say MK2, and a plain title is never matched by an MK2 model. JBL sells the Bar 1000 and the
  Bar 1000MK2 side by side and their codes differ by two characters.
- The listing has to look like a soundbar rather than a subwoofer, a rear-speaker kit or an accessory.
- When several models match, the longest matching alias wins. Rejected models take part as negatives,
  so a "JBL Bar 800MK2" listing is claimed by the rejected 800MK2 rather than by the Bar 800.

Which specs count comes from soundbot.criteria, not from this module.
"""
from __future__ import annotations
import re
from typing import Iterable, Optional

from .criteria import Criteria, looks_like_soundbar, parse_layout
from .watchlist import Model, Rejected

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
# A generation shows up two ways in the same listing: as words ("Bar 800 MK2") and inside the part
# number, where JBL writes it as M2 after the model number ("JBLBAR800M2BLKEP"). Both reduce to "2".
_GENERATION_RE = re.compile(r"MK(III|II|3|2)|(?<=[0-9])M([23])(?![0-9])")
_GENERATION_VALUE = {"III": "3", "II": "2", "3": "3", "2": "2"}
# The shortest alias that may match inside a longer code. Below this it must be a whole word.
EMBED_MIN = 5


def normalize(text: str) -> str:
    t = (text or "").upper()
    t = t.replace("&QUOT;", '"').replace("’", "'").replace("”", '"')
    t = _NON_ALNUM.sub(" ", t)
    return " ".join(t.split())


def _generation(norm: str) -> str:
    """The generation a normalised string carries ('2', '3'), '' when it carries none."""
    m = _GENERATION_RE.search(norm.replace(" ", ""))
    if not m:
        return ""
    return _GENERATION_VALUE.get(m.group(1) or m.group(2), "")


def _generation_clash(norm_title: str, norm_alias: str) -> bool:
    """True when title and alias disagree about the generation (Bar 1000 vs Bar 1000MK2)."""
    t, a = _generation(norm_title), _generation(norm_alias)
    if a:
        return t != a
    # A plain alias may still match a plain title; it must not claim an MK2 listing.
    return bool(t)


def _alias_hits(norm_title: str, alias: str) -> bool:
    a = normalize(alias)
    if not a:
        return False
    if f" {a} " in f" {norm_title} ":
        return True
    if " " not in a and len(a) >= EMBED_MIN and a in norm_title.replace(" ", ""):
        return True
    return False


def is_accessory(title: str) -> bool:
    """A component or accessory sold on its own rather than a soundbar."""
    return not looks_like_soundbar(title)


def match_aliases(title: str, aliases: Iterable[str], crit: Criteria) -> Optional[str]:
    """Return the longest alias that matches the title, or None."""
    if is_accessory(title):
        return None
    norm = normalize(title)
    best: Optional[str] = None
    for alias in aliases:
        if not _alias_hits(norm, alias):
            continue
        if _generation_clash(norm, normalize(alias)):
            continue
        if best is None or len(normalize(alias)) > len(normalize(best)):
            best = alias
    return best


def match_model(title: str, model: Model, crit: Criteria) -> Optional[str]:
    alias = match_aliases(title, model.all_aliases(), crit)
    if alias is None:
        return None
    # A layout printed with no height channels contradicts a watchlist entry that has them, so the shop
    # is selling a different variant: this is what keeps the 7.1 "JBL Bar 800MK2" off the 5.1.2 Bar 800.
    printed = parse_layout(title)
    if printed and printed[2] == 0 and (model.specs.height_channels or 0) > 0:
        return None
    return alias


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
    """Loose filter used by the discovery scan."""
    return crit.looks_like_candidate(title)
