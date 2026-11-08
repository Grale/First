"""Direct company career pages via official ATS job-board APIs.

These are the employers' own published feeds (Greenhouse / Lever / Ashby /
Recruitee), which is the ToS-clean way to read a company career page.
Company tokens live in profile/ats_companies.yaml.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from .base import get_json, is_candidate_title, make_job, too_old

ROOT = Path(__file__).resolve().parent.parent.parent


def _companies(cfg, ats: str) -> list[dict]:
    path = ROOT / cfg["sources"].get("ats_companies_file", "profile/ats_companies.yaml")
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [c for c in (data.get(ats) or []) if c.get("token")]


def _parallel(cfg, ats: str, worker) -> list[dict]:
    comps = _companies(cfg, ats)
    out: list[dict] = []
    if not comps:
        return out
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(worker, cfg, c): c for c in comps}
        for f in as_completed(futs):
            c = futs[f]
            try:
                out.extend(f.result())
            except Exception as exc:                  # noqa: BLE001
                out.append({"_error": f"{ats}/{c['token']}: {type(exc).__name__}"})
    return out


def _finish(cfg, job, comp: dict):
    """Attach curated company metadata the feed cannot know."""
    job.company = job.company or comp.get("name", comp["token"])
    job.industry = comp.get("industry", "") or job.industry
    job.company_size_bucket = comp.get("size", "") or job.company_size_bucket
    if comp.get("employees"):
        job.company_employees_est = comp["employees"]
    if comp.get("gr_entity") is not None:
        job.has_gr_entity = comp["gr_entity"]
    if comp.get("cy_entity") is not None:
        job.has_cy_entity = comp["cy_entity"]
    if comp.get("legal_entity"):
        job.legal_entity = comp["legal_entity"]
    return job


# --------------------------------------------------------------------------
def _gh(cfg, c):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{c['token']}/jobs?content=true",
                    timeout=cfg["sources"]["request_timeout"])
    res = []
    for it in data.get("jobs", []):
        if not is_candidate_title(it.get("title", "")):
            continue
        loc = (it.get("location") or {}).get("name", "")
        offices = ", ".join(o.get("name", "") for o in (it.get("offices") or []) if o.get("name"))
        j = make_job("greenhouse", it.get("id", ""), it.get("absolute_url", ""),
                     it.get("title", ""), c.get("name", it.get("company_name", "")),
                     f"{loc} {offices}".strip(), it.get("content", ""),
                     it.get("first_published") or it.get("updated_at", ""))
        if too_old(j.date_published, cfg["sources"]["max_age_days"]):
            continue
        res.append(_finish(cfg, j, c))
    return res


def _lv(cfg, c):
    data = get_json(f"https://api.lever.co/v0/postings/{c['token']}?mode=json",
                    timeout=cfg["sources"]["request_timeout"])
    res = []
    for it in data:
        if not is_candidate_title(it.get("text", "")):
            continue
        cats = it.get("categories") or {}
        body = (it.get("descriptionPlain") or it.get("description") or "")
        for lst in it.get("lists", []) or []:
            body += f"\n{lst.get('text', '')}\n{lst.get('content', '')}"
        body += f"\n{it.get('additionalPlain', '') or it.get('additional', '')}"
        j = make_job("lever", it.get("id", ""), it.get("hostedUrl", ""), it.get("text", ""),
                     c.get("name", c["token"]),
                     " ".join(filter(None, [cats.get("location"), cats.get("allLocations") and
                                            ", ".join(cats.get("allLocations") or []),
                                            cats.get("commitment"), cats.get("team")])),
                     body, it.get("createdAt", ""))
        if too_old(j.date_published, cfg["sources"]["max_age_days"]):
            continue
        res.append(_finish(cfg, j, c))
    return res


def _ab(cfg, c):
    data = get_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{c['token']}?includeCompensation=true",
        timeout=cfg["sources"]["request_timeout"])
    res = []
    for it in data.get("jobs", []):
        if not is_candidate_title(it.get("title", "")):
            continue
        locs = [it.get("location", "")] + [
            s.get("location", "") for s in (it.get("secondaryLocations") or [])]
        comp = it.get("compensation") or {}
        summary = comp.get("compensationTierSummary") or ""
        j = make_job("ashby", it.get("id", ""), it.get("jobUrl", ""), it.get("title", ""),
                     c.get("name", c["token"]),
                     f"{', '.join(filter(None, locs))} [{it.get('workplaceType', '')}]",
                     it.get("descriptionHtml") or it.get("descriptionPlain", ""),
                     it.get("publishedAt", ""), salary_raw=summary)
        if too_old(j.date_published, cfg["sources"]["max_age_days"]):
            continue
        res.append(_finish(cfg, j, c))
    return res


def _rc(cfg, c):
    data = get_json(f"https://{c['token']}.recruitee.com/api/offers/",
                    timeout=cfg["sources"]["request_timeout"])
    res = []
    for it in data.get("offers", []):
        if not is_candidate_title(it.get("title", "")):
            continue
        loc = ", ".join(filter(None, [it.get("city"), it.get("country")]))
        j = make_job("recruitee", it.get("id", ""),
                     it.get("careers_url") or it.get("careers_apply_url", ""),
                     it.get("title", ""), c.get("name", c["token"]),
                     f"{loc} {it.get('remote') and 'remote' or ''}",
                     it.get("description", "") + (it.get("requirements") or ""),
                     it.get("published_at", ""))
        if too_old(j.date_published, cfg["sources"]["max_age_days"]):
            continue
        res.append(_finish(cfg, j, c))
    return res


def fetch_greenhouse(cfg): return _parallel(cfg, "greenhouse", _gh)
def fetch_lever(cfg):      return _parallel(cfg, "lever", _lv)
def fetch_ashby(cfg):      return _parallel(cfg, "ashby", _ab)
def fetch_recruitee(cfg):  return _parallel(cfg, "recruitee", _rc)
