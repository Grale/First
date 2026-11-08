"""Shared schema.org JobPosting parser.

Several job boards publish a `<script type="application/ld+json">` JobPosting
block on each posting page. That block is the publisher's own structured,
machine-readable description of the job - title, full description, location,
salary, posting date - so it is both the cleanest and the most respectful thing
to read.
"""
from __future__ import annotations

import json
import re

_LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                 re.S | re.I)


def extract(html: str) -> dict | None:
    """Return the first schema.org JobPosting object found in `html`."""
    for block in _LD.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        for obj in _walk(data):
            if isinstance(obj, dict) and obj.get("@type") in ("JobPosting", ["JobPosting"]):
                return obj
    return None


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def location_string(posting: dict) -> str:
    """Flatten jobLocation into 'City, Region, Country'."""
    locs = posting.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    parts: list[str] = []
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        addr = loc.get("address") or {}
        if isinstance(addr, str):
            parts.append(addr)
            continue
        bits = [addr.get("addressLocality"), addr.get("addressRegion"),
                addr.get("addressCountry")]
        bits = [b.get("name") if isinstance(b, dict) else b for b in bits]
        joined = ", ".join(str(b) for b in bits if b)
        if joined:
            parts.append(joined)
    if (posting.get("jobLocationType") or "").upper().startswith("TELECOMMUTE"):
        parts.append("Remote")
    return " | ".join(dict.fromkeys(parts))


def company(posting: dict) -> str:
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        return str(org.get("name") or "")
    return str(org or "")


def salary(posting: dict, months_per_year: int = 12
           ) -> tuple[float | None, float | None, str]:
    """Return (min, max, currency) as ANNUAL figures, or (None, None, '').

    `months_per_year` lets callers apply 13th/14th-salary schemes
    (Austria and Greece commonly pay 14 monthly instalments).
    """
    bs = posting.get("baseSalary")
    if isinstance(bs, list):
        bs = bs[0] if bs else None
    if not isinstance(bs, dict):
        return None, None, ""
    cur = str(bs.get("currency") or bs.get("currencyCode") or "EUR").upper()
    val = bs.get("value")
    if isinstance(val, (int, float)):
        lo = hi = float(val)
        unit = "YEAR"
    elif isinstance(val, dict):
        lo = val.get("minValue", val.get("value"))
        hi = val.get("maxValue", val.get("value"))
        unit = str(val.get("unitText") or "YEAR").upper()
    else:
        return None, None, ""
    try:
        lo = float(lo) if lo is not None else None
        hi = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        return None, None, ""
    if lo is None and hi is None:
        return None, None, ""
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    mult = {"YEAR": 1, "MONTH": months_per_year, "WEEK": 52,
            "DAY": 220, "HOUR": 1720}.get(unit, 1)
    lo, hi = lo * mult, hi * mult
    if lo < 5000 or hi > 2_000_000 or hi < lo:
        return None, None, ""
    return lo, hi, cur
