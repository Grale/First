"""Himalayas - public remote jobs API with explicit location restrictions."""
from __future__ import annotations
from .base import get_json, is_candidate_title, make_job, too_old

NAME = "himalayas"
BASE = "https://himalayas.app/jobs/api"


def fetch(cfg) -> list[dict]:
    out, cursor, pages = [], None, 0
    max_age = cfg["sources"]["max_age_days"]
    while pages < 12:
        url = f"{BASE}?limit=100" + (f"&cursor={cursor}" if cursor else "")
        try:
            data = get_json(url, timeout=cfg["sources"]["request_timeout"])
        except Exception as exc:                      # noqa: BLE001
            out.append({"_error": str(exc)})
            break
        jobs = data.get("jobs") or data.get("data") or []
        for it in jobs:
            if not is_candidate_title(it.get("title", "")):
                continue
            loc = ", ".join(it.get("locationRestrictions") or []) or "Remote"
            per = (it.get("salaryPeriod") or "").lower()
            smin, smax = it.get("minSalary"), it.get("maxSalary")
            if per and per not in ("annual", "yearly", "year"):
                smin = smax = None
            j = make_job(NAME, it.get("guid", it.get("applicationLink", "")),
                         it.get("applicationLink", "") or it.get("guid", ""),
                         it.get("title", ""), it.get("companyName", ""), loc,
                         it.get("description", ""), it.get("pubDate", ""),
                         (it.get("categories") or []) + (it.get("seniority") or []),
                         sal_min=smin, sal_max=smax, currency=it.get("currency", "USD"))
            j.remote_countries = [c for c in (it.get("locationRestrictions") or [])]
            if too_old(j.date_published, max_age):
                continue
            out.append(j)
        cursor = data.get("nextCursor")
        pages += 1
        if not cursor or not jobs:
            break
    return out
