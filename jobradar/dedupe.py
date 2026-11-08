"""Deduplication: canonical URL first, then fuzzy company+title+country."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Job

_NOISE = re.compile(
    r"\b(m/f/d|m/w/d|all genders|f/m/x|m/f/x|w/m/d|all genders welcome|remote|hybrid|"
    r"full[- ]time|part[- ]time|permanent|contract|fixed term|\d{2,}%|eu|emea|"
    r"onsite|on[- ]site)\b", re.IGNORECASE)
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SUFFIX = re.compile(
    r"\b(gmbh|ltd|limited|llc|inc|plc|ag|sa|s\.a\.|bv|b\.v\.|nv|oy|ab|as|aps|"
    r"srl|spa|sarl|kft|zrt|ltda|pte|co|corp|corporation|holdings?|group|"
    r"technologies|technology|solutions|services|international)\b", re.IGNORECASE)


def norm_title(title: str) -> str:
    t = _NOISE.sub(" ", (title or "").lower())
    t = re.sub(r"\(.*?\)", " ", t)
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


def norm_company(name: str) -> str:
    c = _SUFFIX.sub(" ", (name or "").lower())
    c = _PUNCT.sub(" ", c)
    return " ".join(c.split())


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def dedupe(jobs: list[Job], title_threshold: float = 0.88,
           company_threshold: float = 0.90) -> tuple[list[Job], int]:
    """Collapse duplicates. Keeps the record with the longest description
    (best data), merging the source list into `tags`. Returns (kept, removed)."""
    by_url: dict[str, Job] = {}
    order: list[str] = []
    for j in jobs:
        key = j.canonical_url or j.fingerprint()
        if key in by_url:
            _merge(by_url[key], j)
        else:
            by_url[key] = j
            order.append(key)
    stage1 = [by_url[k] for k in order]

    kept: list[Job] = []
    for j in stage1:
        nt, nc = norm_title(j.title), norm_company(j.company)
        hit = None
        for k in kept:
            if not nc or not norm_company(k.company):
                continue
            if (similar(nc, norm_company(k.company)) >= company_threshold
                    and similar(nt, norm_title(k.title)) >= title_threshold
                    and (j.country or "") == (k.country or "")):
                hit = k
                break
        if hit is None:
            kept.append(j)
        else:
            _merge(hit, j)
    return kept, len(jobs) - len(kept)


def _merge(keep: Job, other: Job) -> None:
    """Fold `other` into `keep`, preferring richer data."""
    if len(other.description) > len(keep.description):
        keep.description = other.description
        keep.description_html = other.description_html or keep.description_html
    tag = f"also_on:{other.source}"
    if tag not in keep.tags and other.source != keep.source:
        keep.tags.append(tag)
    for attr in ("date_published", "published_salary_raw", "raw_location", "legal_entity"):
        if not getattr(keep, attr) and getattr(other, attr):
            setattr(keep, attr, getattr(other, attr))
    if keep.salary_published_min is None and other.salary_published_min is not None:
        keep.salary_published_min = other.salary_published_min
        keep.salary_published_max = other.salary_published_max
        keep.salary_currency = other.salary_currency
