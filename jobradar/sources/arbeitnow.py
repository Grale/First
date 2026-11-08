"""Arbeitnow - public job-board API, Europe/DACH heavy (good AT coverage)."""
from __future__ import annotations
from .base import get_json, is_candidate_title, make_job, too_old

NAME = "arbeitnow"
BASE = "https://www.arbeitnow.com/api/job-board-api"


def fetch(cfg) -> list[dict]:
    out, page, seen = [], 1, set()
    while page <= 20:
        try:
            data = get_json(f"{BASE}?page={page}", timeout=cfg["sources"]["request_timeout"])
        except Exception as exc:                      # noqa: BLE001
            out.append({"_error": f"page {page}: {exc}"})
            break
        items = data.get("data", [])
        if not items:
            break
        for it in items:
            slug = it.get("slug", "")
            if slug in seen or not is_candidate_title(it.get("title", "")):
                continue
            seen.add(slug)
            tags = (it.get("tags") or []) + (it.get("job_types") or [])
            if it.get("remote"):
                tags.append("remote")
            j = make_job(NAME, slug, it.get("url", ""), it.get("title", ""),
                         it.get("company_name", ""), it.get("location", ""),
                         it.get("description", ""), it.get("created_at", ""), tags)
            if too_old(j.date_published, cfg["sources"]["max_age_days"]):
                continue
            out.append(j)
        page += 1
    return out
