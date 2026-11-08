"""Workable - public job-board API for employers hosted on Workable.

Most Greek tech employers (Persado, Skroutz, Blueground, Viva Wallet,
Hellas Direct and many more) publish through Workable, which makes this the
single highest-value source for Greek coverage.

Permitted: workable.com/robots.txt carries
`Content-Signal: search=yes, ai-input=yes, ai-train=no` and disallows only
/j/, /admin, /auth/google and /user_password_resets. This adapter uses the
documented public account endpoints, not /j/.

IMPORTANT - known environment limitation: apply.workable.com returns HTTP 429
to every request from this project's cloud egress IP, including robots.txt.
That is infrastructure rate-limiting on a shared datacenter address, not a
policy decision about this project. The adapter is expected to work normally
from a residential IP, so run it locally if Greek coverage matters.

Company accounts are listed in profile/workable_companies.yaml.
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml

from .base import get_json, is_candidate_title, make_job, too_old

NAME = "workable"
ROOT = Path(__file__).resolve().parent.parent.parent

# Documented public endpoints, tried in order.
ENDPOINTS = [
    "https://apply.workable.com/api/v1/widget/accounts/{acct}?details=true",
    "https://apply.workable.com/api/v3/accounts/{acct}/jobs",
]


def _accounts(cfg) -> list[dict]:
    path = ROOT / "profile" / "workable_companies.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [c for c in (data.get("workable") or []) if c.get("token")]


def fetch(cfg) -> list[dict]:
    timeout = cfg["sources"]["request_timeout"]
    out: list[dict] = []
    blocked = 0
    consecutive_429 = 0
    accounts = _accounts(cfg)

    for comp in accounts:
        # Circuit breaker: if the egress IP is rate-limited there is no point
        # walking the whole list - bail out after 5 consecutive 429s.
        if consecutive_429 >= 5:
            out.append({"_error":
                        f"aborted after {consecutive_429} consecutive HTTP 429s - "
                        f"this egress IP is rate-limited by apply.workable.com "
                        f"({len(accounts) - blocked} accounts not attempted)"})
            return out
        acct = comp["token"]
        jobs = None
        hit_429 = False
        for tmpl in ENDPOINTS:
            try:
                data = get_json(tmpl.format(acct=acct), timeout=timeout, retries=0)
            except Exception as exc:                  # noqa: BLE001
                if "429" in str(exc):
                    hit_429 = True
                continue
            jobs = data.get("jobs") if isinstance(data, dict) else None
            if jobs:
                break
        if hit_429:
            blocked += 1
            consecutive_429 += 1
        elif jobs:
            consecutive_429 = 0
        if not jobs:
            continue
        for it in jobs:
            title = it.get("title", "")
            if not is_candidate_title(title):
                continue
            loc = it.get("location") or {}
            if isinstance(loc, dict):
                loc_s = ", ".join(str(v) for v in (
                    loc.get("city"), loc.get("region"), loc.get("country")) if v)
                if loc.get("workplace") or loc.get("telecommuting"):
                    loc_s += f" [{loc.get('workplace') or 'remote'}]"
            else:
                loc_s = str(loc)
            url = (it.get("url") or it.get("application_url")
                   or f"https://apply.workable.com/{acct}/j/{it.get('shortcode', '')}/")
            j = make_job(NAME, it.get("id") or it.get("shortcode", ""), url, title,
                         comp.get("name", acct), loc_s,
                         it.get("description", "") + (it.get("requirements") or ""),
                         it.get("published_on") or it.get("created_at", ""))
            j.industry = comp.get("industry", "") or j.industry
            j.company_size_bucket = comp.get("size", "") or j.company_size_bucket
            if comp.get("employees"):
                j.company_employees_est = comp["employees"]
            if comp.get("gr_entity") is not None:
                j.has_gr_entity = comp["gr_entity"]
            if comp.get("cy_entity") is not None:
                j.has_cy_entity = comp["cy_entity"]
            if too_old(j.date_published, cfg["sources"]["max_age_days"]):
                continue
            out.append(j)
        time.sleep(0.4)

    if blocked:
        out.append({"_error":
                    f"apply.workable.com returned HTTP 429 for {blocked}/{len(accounts)} "
                    "accounts - this egress IP is rate-limited; run from a "
                    "residential IP for Greek coverage"})
    return out
