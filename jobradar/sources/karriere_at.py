"""karriere.at - Austria's largest job board.

Permitted: robots.txt carries `User-agent: * / Disallow:` (an empty Disallow,
i.e. everything allowed) and publishes sitemaps for crawling. No Content-Signal
restrictions and no AI-agent-specific rules.

Politeness: titles are filtered on the search-results page first, so a detail
page is only fetched for postings that are actually candidates - typically
10-25 requests per run rather than hundreds. Requests are paced and
concurrency is capped at 3.

Austrian law requires salary disclosure, so the schema.org `baseSalary` field
is usually populated: these are HIGH-confidence published salaries.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from . import jsonld
from .base import get_text, is_candidate_title, make_job, too_old

NAME = "karriere_at"
SEARCH = "https://www.karriere.at/jobs?keywords={q}"

# Pagination is AJAX-only, so breadth comes from targeted keywords instead.
QUERIES = [
    "head of data", "data analytics", "business intelligence", "data engineering",
    "data warehouse", "datenmanagement", "data platform", "leitung daten",
    "teamleiter data", "bi manager", "analytics manager", "data architect",
    "leitung business intelligence", "data governance", "datenanalyse",
]
MAX_DETAIL = 60

# Austrian law obliges employers to state the collective-agreement MINIMUM
# ("kollektivvertragliches Mindestgehalt"), which is routinely far below the
# real offer - most ads then add "Überzahlung" / "deutlich über". Treating that
# number as the salary would wrongly exclude good roles on a legal formality.
KV_MINIMUM = re.compile(
    r"(kollektivvertrag|kollektivvertragl|mindestgehalt|mindestentgelt|"
    r"gesetzlichen gründen|überzahlung|ueberzahlung|mindestens eur|ab eur|"
    r"deutlich über|marktkonform|tatsächliche[s]? gehalt|gehalt bereden|"
    r"bereden wir|persönlichen gespräch|verhandlungsbasis|"
    r"je nach (qualifikation|erfahrung|berufserfahrung)|"
    r"gehalt.{0,40}(besprechen|vereinbaren|abhängig))", re.I)


def fetch(cfg) -> list[dict]:
    timeout = cfg["sources"]["request_timeout"]
    seen: dict[str, dict] = {}
    errors: list[str] = []

    for q in QUERIES:
        try:
            html = get_text(SEARCH.format(q=q.replace(" ", "+")), timeout=timeout)
        except Exception as exc:                      # noqa: BLE001
            errors.append(f"{q}: {type(exc).__name__}")
            continue
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select(".m-jobsListItem"):
            a = card.select_one("a[href]")
            if not a:
                continue
            url = a["href"]
            if not url.startswith("http"):
                url = "https://www.karriere.at" + url
            jid = url.rstrip("/").rsplit("/", 1)[-1]
            if jid in seen:
                continue
            t_el = card.select_one("h2") or card.select_one(".m-jobsListItem__title")
            title = t_el.get_text(" ", strip=True) if t_el else ""
            if not is_candidate_title(title):
                continue
            c_el = card.select_one(".m-jobsListItem__company")
            l_el = card.select_one(".m-jobsListItem__locations")
            seen[jid] = {
                "url": url, "title": title,
                "company": c_el.get_text(" ", strip=True) if c_el else "",
                "location": (l_el.get_text(" ", strip=True).strip(" ,") if l_el else ""),
            }
        time.sleep(0.6)

    targets = list(seen.items())[:MAX_DETAIL]
    out: list[dict] = []

    def detail(item):
        jid, meta = item
        try:
            html = get_text(meta["url"], timeout=timeout)
        except Exception:                             # noqa: BLE001
            return None
        post = jsonld.extract(html) or {}
        desc = post.get("description") or ""
        if not desc:
            soup = BeautifulSoup(html, "lxml")
            el = soup.select_one(".m-jobContent__jobText") or soup.select_one(".m-jobContent")
            desc = el.decode_contents() if el else ""
        loc = jsonld.location_string(post) or meta["location"]
        j = make_job(NAME, jid, meta["url"], post.get("title") or meta["title"],
                     jsonld.company(post) or meta["company"], loc, desc,
                     post.get("datePosted", ""))
        # Austria pays 14 monthly instalments, so a monthly figure annualises
        # at x14, not x12.
        lo, hi, cur = jsonld.salary(post, months_per_year=14)
        if lo:
            from ..normalize import _FX_TO_EUR
            rate = _FX_TO_EUR.get(cur, 1.0)
            j.salary_published_min = round(lo * rate)
            j.salary_published_max = round(hi * rate)
            j.salary_currency = cur
            # Austrian ads must publish the collective-agreement minimum.
            # Two signals that the figure is a floor rather than the offer:
            #   (a) explicit KV / "actual salary to be discussed" wording, or
            #   (b) a single exact point rather than a range - real offers are
            #       quoted as ranges; KV table values are exact (often to the
            #       cent, e.g. EUR 43,465.52).
            # A SINGLE-POINT value is the collective-agreement minimum: real
            # offers are quoted as ranges, KV table values are exact (often to
            # the cent, e.g. EUR 43,465.52). A stated RANGE is the employer's
            # actual band and is kept as published, even when the ad also
            # carries the mandatory KV wording.
            kv_wording = bool(KV_MINIMUM.search(j.description[:12000]))
            is_floor = j.salary_published_min == j.salary_published_max
            j.salary_is_floor = is_floor
            j.published_salary_raw = (
                f"{cur} {lo:,.0f}-{hi:,.0f}/yr "
                + ("(collective-agreement MINIMUM - actual offer typically "
                   "well above)" if is_floor
                   else "(employer-stated range" +
                        (", ad also carries the mandatory KV minimum wording)"
                         if kv_wording else ")")))
            if is_floor:
                j.tags.append("kv_minimum")
        return j

    with ThreadPoolExecutor(max_workers=3) as ex:
        for j in ex.map(detail, targets):
            if j is None:
                continue
            if too_old(j.date_published, cfg["sources"]["max_age_days"]):
                continue
            out.append(j)

    if errors:
        out.append({"_error": "; ".join(errors[:3])})
    return out
