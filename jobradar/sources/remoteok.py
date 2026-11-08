"""Remote OK - public API. Attribution required by their ToS (see README)."""
from __future__ import annotations
from .base import get_json, is_candidate_title, make_job, too_old

NAME = "remoteok"
URL = "https://remoteok.com/api"


def fetch(cfg) -> list[dict]:
    out = []
    try:
        data = get_json(URL, timeout=cfg["sources"]["request_timeout"])
    except Exception as exc:                          # noqa: BLE001
        return [{"_error": str(exc)}]
    for it in data:
        if not isinstance(it, dict) or "position" not in it:
            continue                                   # first element is the legal notice
        if not is_candidate_title(it.get("position", "")):
            continue
        smin, smax = it.get("salary_min") or 0, it.get("salary_max") or 0
        j = make_job(NAME, it.get("id", ""), it.get("url") or it.get("apply_url", ""),
                     it.get("position", ""), it.get("company", ""),
                     it.get("location", "") or "Remote", it.get("description", ""),
                     it.get("date", ""), it.get("tags") or [],
                     sal_min=smin or None, sal_max=smax or None, currency="USD")
        if too_old(j.date_published, cfg["sources"]["max_age_days"]):
            continue
        out.append(j)
    return out
