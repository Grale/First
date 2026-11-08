"""Working Nomads - public exposed_jobs feed."""
from __future__ import annotations
from .base import get_json, is_candidate_title, make_job, too_old

NAME = "workingnomads"
URL = "https://www.workingnomads.com/api/exposed_jobs/"


def fetch(cfg) -> list[dict]:
    try:
        data = get_json(URL, timeout=cfg["sources"]["request_timeout"])
    except Exception as exc:                          # noqa: BLE001
        return [{"_error": str(exc)}]
    out = []
    for it in data:
        if not is_candidate_title(it.get("title", "")):
            continue
        tags = [t.strip() for t in (it.get("tags") or "").split(",") if t.strip()]
        j = make_job(NAME, it.get("url", ""), it.get("url", ""), it.get("title", ""),
                     it.get("company_name", ""), it.get("location", "") or "Remote",
                     it.get("description", ""), it.get("pub_date", ""), tags)
        if it.get("location"):
            j.remote_countries = [c.strip() for c in it["location"].split(",") if c.strip()]
        if too_old(j.date_published, cfg["sources"]["max_age_days"]):
            continue
        out.append(j)
    return out
