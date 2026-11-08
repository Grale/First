"""Jobicy - public remote jobs API v2. Credit required by their ToS."""
from __future__ import annotations
from .base import get_json, is_candidate_title, make_job, too_old

NAME = "jobicy"
BASE = "https://jobicy.com/api/v2/remote-jobs"
GEOS = ["europe", "anywhere", "greece", "austria", "cyprus"]


def fetch(cfg) -> list[dict]:
    out, seen = [], set()
    for geo in GEOS:
        for tag in ("data", "analytics", "engineering", "business"):
            try:
                data = get_json(f"{BASE}?count=50&geo={geo}&tag={tag}",
                                timeout=cfg["sources"]["request_timeout"])
            except Exception as exc:                  # noqa: BLE001
                out.append({"_error": f"{geo}/{tag}: {exc}"})
                continue
            for it in data.get("jobs", []):
                jid = str(it.get("id"))
                if jid in seen or not is_candidate_title(it.get("jobTitle", "")):
                    continue
                seen.add(jid)
                per = (it.get("salaryPeriod") or "").lower()
                smin = it.get("salaryMin") if per in ("yearly", "annual", "year") else None
                smax = it.get("salaryMax") if per in ("yearly", "annual", "year") else None
                j = make_job(NAME, jid, it.get("url", ""), it.get("jobTitle", ""),
                             it.get("companyName", ""), it.get("jobGeo", ""),
                             it.get("jobDescription", "") or it.get("jobExcerpt", ""),
                             it.get("pubDate", ""),
                             (it.get("jobIndustry") or []) + (it.get("jobType") or []),
                             sal_min=smin, sal_max=smax,
                             currency=it.get("salaryCurrency", "USD"))
                if too_old(j.date_published, cfg["sources"]["max_age_days"]):
                    continue
                out.append(j)
    return out
