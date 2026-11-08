"""Carierista - the main Cyprus job board.

Permitted: robots.txt is `User-agent: * / Disallow:` - an empty Disallow,
which allows everything. No Content-Signal restrictions, no AI-agent rules.

Each posting page carries a schema.org JobPosting block including an
`industry` field, which carierista populates with values such as
"Fintech, Forex & Crypto" - a far more reliable Forex signal than inferring it
from the description.

Politeness: category listings are filtered by title first; detail pages are
only fetched for actual candidates.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import jsonld
from .base import get_text, is_candidate_title, make_job, too_old

NAME = "carierista"
BASE = "https://www.carierista.com"
CATEGORIES = [
    "technology-it-telecommunications",
    "banking-financial-services",
    "management-executive",
    "accountancy-auditing",
    "marketing-advertising-pr",
    "engineering",
]
JOB_LINK = re.compile(r'href="(https://www\.carierista\.com/en/jobs/\d+/[^"#?]+)"')
MAX_DETAIL = 60
MAX_PAGES = 8      # 10 postings per page

# carierista's own industry taxonomy -> our internal industry keys
INDUSTRY_MAP = {
    "forex": "forex_cfd", "crypto": "forex_cfd",
    "bank": "fintech_banking", "financial": "fintech_banking",
    "insurance": "fintech_banking", "audit": "consulting",
    "accountanc": "consulting", "consult": "consulting",
    "telecom": "telecom", "technology": "technology_saas",
    "it &": "technology_saas", "software": "technology_saas",
    "retail": "ecommerce_retail", "ecommerce": "ecommerce_retail",
    "shipping": "logistics", "logistics": "logistics", "maritime": "logistics",
    "energy": "energy", "health": "healthcare", "pharma": "healthcare",
    "manufactur": "manufacturing", "gaming": "gaming_igaming",
    "betting": "gaming_igaming", "public": "public_nonprofit",
}


def _map_industry(raw: str) -> str:
    low = (raw or "").lower()
    for needle, key in INDUSTRY_MAP.items():
        if needle in low:
            return key
    return ""


def fetch(cfg) -> list[dict]:
    timeout = cfg["sources"]["request_timeout"]
    links: list[str] = []
    errors: list[str] = []

    for cat in CATEGORIES:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE}/en/jobs/search/any/{cat}"
            if page > 1:
                url += f"?page={page}"
            try:
                html = get_text(url, timeout=timeout)
            except Exception as exc:                  # noqa: BLE001
                errors.append(f"{cat} p{page}: {type(exc).__name__}")
                break
            found = JOB_LINK.findall(html)
            if not found:
                break
            new = [u for u in found if u not in links]
            links.extend(new)
            time.sleep(0.5)
            if not new:                 # paged past the end
                break

    # Pre-filter on the slug, which mirrors the job title, so we only open
    # detail pages for plausible candidates.
    def slug_title(u: str) -> str:
        return u.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")

    candidates = [u for u in links if is_candidate_title(slug_title(u))][:MAX_DETAIL]
    out: list[dict] = []

    def detail(url: str):
        try:
            html = get_text(url, timeout=timeout)
        except Exception:                             # noqa: BLE001
            return None
        post = jsonld.extract(html)
        if not post:
            return None
        title = post.get("title") or slug_title(url).title()
        if not is_candidate_title(title):
            return None
        jid = url.rstrip("/").split("/")[-2]
        loc = jsonld.location_string(post) or "Cyprus"
        j = make_job(NAME, jid, url, title, jsonld.company(post), loc,
                     post.get("description", ""), post.get("datePosted", ""))
        mapped = _map_industry(str(post.get("industry") or ""))
        if mapped:
            j.industry = mapped
            j.tags.append(f"industry_declared:{str(post.get('industry'))[:60]}")
        cats = post.get("occupationalCategory")
        if cats:
            j.tags.append(f"category:{str(cats)[:80]}")
        lo, hi, cur = jsonld.salary(post)
        if lo:
            from ..normalize import _FX_TO_EUR
            rate = _FX_TO_EUR.get(cur, 1.0)
            j.salary_published_min = round(lo * rate)
            j.salary_published_max = round(hi * rate)
            j.salary_currency = cur
            j.published_salary_raw = f"{cur} {lo:,.0f}-{hi:,.0f} (schema.org baseSalary)"
        return j

    with ThreadPoolExecutor(max_workers=3) as ex:
        for j in ex.map(detail, candidates):
            if j is None:
                continue
            if too_old(j.date_published, cfg["sources"]["max_age_days"]):
                continue
            out.append(j)

    if errors:
        out.append({"_error": "; ".join(errors[:3])})
    return out
