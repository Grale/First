"""Shared HTTP + relevance prefilter for all source adapters."""
from __future__ import annotations

import html as _html
import logging
import re
import time
from datetime import date, datetime, timedelta

import requests

from ..normalize import canonical_url, clean_text, html_to_text, parse_date, parse_salary
from ..models import Job

log = logging.getLogger("jobradar.sources")

UA = {"User-Agent": "job-discovery-poc/0.1 (personal job search; contact via application)",
      "Accept": "application/json, text/plain, */*"}

_SESSION = requests.Session()
_SESSION.headers.update(UA)

# ---------------------------------------------------------------------------
# Relevance prefilter. Deliberately WIDE - the scoring engine does the real
# work. This only stops us carrying tens of thousands of unrelated postings.
# ---------------------------------------------------------------------------
ROLE_WORDS = r"(data|analytics|analytic|bi\b|business intelligence|warehouse|warehousing|insight|reporting|platform)"
LEAD_WORDS = (r"(head|director|vp|vice president|chief|lead|leader|manager|management|"
              r"principal|staff|owner|architect|governance)")

_RELEVANT = re.compile(rf"{ROLE_WORDS}", re.IGNORECASE)
_LEADERSHIP = re.compile(rf"{LEAD_WORDS}", re.IGNORECASE)

# Titles that are never a fit regardless of leadership wording.
_HARD_TITLE_NOISE = re.compile(
    r"\b(nurse|driver|teacher|chef|sales representative|account executive|recruiter|"
    r"customer (service|support|success)|barista|warehouse (operative|associate|worker|picker)|"
    r"truck|forklift|janitor|security guard|social media|copywriter|designer|"
    r"paralegal|accountant|bookkeep|physician|therapist|dental|pharmacist|"
    r"solar|electrician|plumber|technician ii|call cent)", re.IGNORECASE)


def is_candidate_title(title: str) -> bool:
    """Wide gate: data-ish AND leadership-ish, minus obvious noise."""
    t = title or ""
    if _HARD_TITLE_NOISE.search(t):
        return False
    return bool(_RELEVANT.search(t) and _LEADERSHIP.search(t))


def get_json(url: str, timeout: int = 30, retries: int = 2, **kw):
    last = None
    for attempt in range(retries + 1):
        try:
            r = _SESSION.get(url, timeout=timeout, **kw)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                last = RuntimeError("429 rate limited")
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:                      # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError("request failed")


def get_text(url: str, timeout: int = 30, retries: int = 2, **kw) -> str:
    last = None
    for attempt in range(retries + 1):
        try:
            r = _SESSION.get(url, timeout=timeout, **kw)
            r.raise_for_status()
            return r.text
        except Exception as exc:                      # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError("request failed")


def unescape_html(s: str) -> str:
    """Some feeds double-escape their HTML payload."""
    if s and "&lt;" in s:
        s = _html.unescape(s)
    return s or ""


def too_old(iso_date: str, max_age_days: int) -> bool:
    if not iso_date:
        return False                 # unknown date -> keep, flag later
    try:
        d = datetime.fromisoformat(iso_date).date()
    except ValueError:
        return False
    return d < (date.today() - timedelta(days=max_age_days))


def make_job(source: str, source_id: str, url: str, title: str, company: str,
             location: str, description_html: str, published: str,
             tags: list[str] | None = None, salary_raw: str = "",
             sal_min=None, sal_max=None, currency: str = "") -> Job:
    desc_html = unescape_html(description_html or "")
    text = html_to_text(desc_html)
    j = Job(
        source=source, source_id=str(source_id), url=url,
        canonical_url=canonical_url(url),
        title=clean_text(title or "")[:300],
        company=clean_text(company or "")[:200],
        raw_location=clean_text(location or "")[:300],
        description=text, description_html=desc_html[:200000],
        date_published=parse_date(published),
        date_discovered=date.today().isoformat(),
        tags=list(tags or []),
        published_salary_raw=salary_raw or "",
    )
    # published salary: explicit fields win, else parse the raw string / JD head
    if sal_min and sal_max:
        from ..normalize import _FX_TO_EUR
        rate = _FX_TO_EUR.get((currency or "EUR").upper(), 1.0)
        j.salary_published_min = round(float(sal_min) * rate)
        j.salary_published_max = round(float(sal_max) * rate)
        j.salary_currency = (currency or "EUR").upper()
    else:
        lo, hi, cur, raw = parse_salary(f"{salary_raw}\n{text[:4000]}")
        if lo:
            j.salary_published_min, j.salary_published_max = lo, hi
            j.salary_currency = cur
            j.published_salary_raw = j.published_salary_raw or raw
    return j
