"""We Work Remotely - official public RSS category feeds."""
from __future__ import annotations

from xml.etree import ElementTree as ET

from .base import get_text, is_candidate_title, make_job, too_old

NAME = "weworkremotely"
FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
    "https://weworkremotely.com/categories/all-other-remote-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-product-jobs.rss",
]


def fetch(cfg) -> list[dict]:
    out, seen = [], set()
    for feed in FEEDS:
        try:
            xml = get_text(feed, timeout=cfg["sources"]["request_timeout"])
            root = ET.fromstring(xml.encode("utf-8"))
        except Exception as exc:                      # noqa: BLE001
            out.append({"_error": f"{feed.rsplit('/', 1)[-1]}: {exc}"})
            continue
        for item in root.iter("item"):
            def g(tag: str) -> str:
                el = item.find(tag)
                return (el.text or "").strip() if el is not None and el.text else ""
            link, raw_title = g("link"), g("title")
            if link in seen:
                continue
            seen.add(link)
            # WWR titles are "Company: Role"
            company, _, title = raw_title.partition(":")
            title, company = (title.strip() or raw_title), company.strip()
            if not is_candidate_title(title):
                continue
            region = g("region") or g("{https://weworkremotely.com/}region") or "Remote"
            j = make_job(NAME, link, link, title, company, region,
                         g("description"), g("pubDate"))
            if too_old(j.date_published, cfg["sources"]["max_age_days"]):
                continue
            out.append(j)
    return out
