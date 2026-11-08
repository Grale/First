"""Remotive - public remote-jobs API (https://remotive.com/api/remote-jobs).

NOTE: the free tier now returns only a handful of live postings and its
`search` parameter does full-text ranking rather than filtering (searching
"head of data" returns customer-service roles). We therefore pull the whole
feed and filter locally.
"""
from __future__ import annotations
from .base import get_json, is_candidate_title, make_job, too_old

NAME = "remotive"
BASE = "https://remotive.com/api/remote-jobs"


def fetch(cfg) -> list[dict]:
    out = []
    try:
        data = get_json(BASE, timeout=cfg["sources"]["request_timeout"])
    except Exception as exc:                          # noqa: BLE001
        return [{"_error": str(exc)}]
    for it in data.get("jobs", []):
        if not is_candidate_title(it.get("title", "")):
            continue
        j = make_job(NAME, it.get("id", ""), it.get("url", ""), it.get("title", ""),
                     it.get("company_name", ""), it.get("candidate_required_location", ""),
                     it.get("description", ""), it.get("publication_date", ""),
                     it.get("tags") or [], salary_raw=it.get("salary", "") or "")
        if too_old(j.date_published, cfg["sources"]["max_age_days"]):
            continue
        out.append(j)
    return out
