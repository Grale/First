"""LinkedIn job postings, via LinkedIn's own job-alert emails.

Why this route
--------------
LinkedIn's robots.txt is unambiguous: "The use of robots or other automated
means to access LinkedIn without the express permission of LinkedIn is
strictly prohibited." So this project does not crawl LinkedIn.

It does not need to. When you create a saved job search on LinkedIn, LinkedIn
emails the matching jobs to you. Those emails are your own mail, delivered to
you deliberately by LinkedIn, and reading your own inbox is not scraping. This
adapter parses them.

Setup
-----
1. On LinkedIn, run the searches you care about and switch the job alert ON
   for each, set to Daily. Suggested searches:
      - "Head of Data"            location: European Union      remote
      - "Head of Data Platform"   location: Greece / Cyprus / Austria
      - "Head of Business Intelligence"
      - "Analytics Engineering Manager"
      - "Data Engineering Manager"
2. Give the app read access to the mailbox those alerts land in:

       export LINKEDIN_IMAP_HOST=imap.gmail.com
       export LINKEDIN_IMAP_USER=you@gmail.com
       export LINKEDIN_IMAP_PASSWORD=<16-char Gmail app password>

   Use a Google *app password*, not your account password, and prefer a
   dedicated filter/label so the app only ever sees job alerts:

       export LINKEDIN_IMAP_FOLDER="Job Alerts"

Offline alternative: drop saved .eml or .html alert files into a directory and
point LINKEDIN_ALERT_DIR at it - no mailbox credentials needed.
"""
from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

from bs4 import BeautifulSoup

from .base import is_candidate_title, make_job, too_old
from ..normalize import canonical_url

NAME = "linkedin_alerts"

JOB_VIEW = re.compile(r"https://[a-z.]*linkedin\.com/comm/jobs/view/(\d+)", re.I)
JOB_VIEW_ANY = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.I)


def _decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:                                 # noqa: BLE001
        return value or ""


def _bodies_from_imap(cfg) -> list[tuple[str, str]]:
    host = os.environ.get("LINKEDIN_IMAP_HOST")
    user = os.environ.get("LINKEDIN_IMAP_USER")
    pwd = os.environ.get("LINKEDIN_IMAP_PASSWORD")
    folder = os.environ.get("LINKEDIN_IMAP_FOLDER", "INBOX")
    if not (host and user and pwd):
        return []
    since = (date.today() - timedelta(days=cfg["sources"]["max_age_days"])).strftime("%d-%b-%Y")
    out: list[tuple[str, str]] = []
    conn = imaplib.IMAP4_SSL(host)
    try:
        conn.login(user, pwd)
        conn.select(f'"{folder}"', readonly=True)
        typ, data = conn.search(None, f'(SINCE {since} FROM "linkedin.com")')
        if typ != "OK":
            return []
        for num in (data[0].split() if data and data[0] else []):
            typ, raw = conn.fetch(num, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            subject = _decode(msg.get("Subject", ""))
            sent = msg.get("Date", "")
            html = ""
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        html = part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", "replace")
                    except Exception:                 # noqa: BLE001
                        continue
                    break
            if html:
                out.append((html, _rfc_date(sent)))
    finally:
        try:
            conn.logout()
        except Exception:                             # noqa: BLE001
            pass
    return out


def _bodies_from_dir() -> list[tuple[str, str]]:
    d = os.environ.get("LINKEDIN_ALERT_DIR")
    if not d or not Path(d).is_dir():
        return []
    out = []
    for p in sorted(Path(d).glob("*")):
        if p.suffix.lower() not in (".eml", ".html", ".htm"):
            continue
        raw = p.read_bytes()
        if p.suffix.lower() == ".eml":
            msg = email.message_from_bytes(raw)
            sent = _rfc_date(msg.get("Date", ""))
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        out.append((part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", "replace"), sent))
                    except Exception:                 # noqa: BLE001
                        pass
                    break
        else:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).date().isoformat()
            out.append((raw.decode("utf-8", "replace"), mtime))
    return out


def _rfc_date(value: str) -> str:
    try:
        return email.utils.parsedate_to_datetime(value).date().isoformat()
    except Exception:                                 # noqa: BLE001
        return ""


def parse_alert(html: str, received: str) -> list:
    """Extract job cards from one LinkedIn job-alert email."""
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, dict] = {}

    for a in soup.find_all("a", href=True):
        m = JOB_VIEW_ANY.search(a["href"])
        if not m:
            continue
        jid = m.group(1)
        text = a.get_text(" ", strip=True)
        if not text or len(text) < 3:
            continue
        if jid in found and found[jid]["title"]:
            continue
        # LinkedIn renders the card as: title link, then company · location
        block = a.find_parent(["td", "tr", "table", "div"])
        ctx = block.get_text("\n", strip=True) if block else text
        lines = [l for l in ctx.split("\n") if l.strip()]
        title = text
        company, location = "", ""
        if title in lines:
            i = lines.index(title)
            rest = lines[i + 1:i + 4]
            if rest:
                # "Company · Location" or separate lines
                first = rest[0]
                if "·" in first:
                    company, _, location = first.partition("·")
                else:
                    company = first
                    if len(rest) > 1:
                        location = rest[1]
        found[jid] = {
            "title": title.strip(),
            "company": company.strip(),
            "location": location.strip(),
            "url": f"https://www.linkedin.com/jobs/view/{jid}/",
        }

    jobs = []
    for jid, meta in found.items():
        if not is_candidate_title(meta["title"]):
            continue
        j = make_job(NAME, jid, meta["url"], meta["title"], meta["company"],
                     meta["location"], "", received)
        j.canonical_url = canonical_url(meta["url"])
        j.assessment_complete = False
        j.missing_info.append(
            "Discovered via a LinkedIn job-alert email: title, company and "
            "location only. Open the posting to read the full description - "
            "the score is based on limited evidence.")
        j.tags.append("from_email_alert")
        jobs.append(j)
    return jobs


def fetch(cfg) -> list[dict]:
    bodies: list[tuple[str, str]] = []
    errors: list[str] = []
    try:
        bodies += _bodies_from_imap(cfg)
    except Exception as exc:                          # noqa: BLE001
        errors.append(f"imap: {type(exc).__name__}: {str(exc)[:80]}")
    try:
        bodies += _bodies_from_dir()
    except Exception as exc:                          # noqa: BLE001
        errors.append(f"dir: {type(exc).__name__}")

    if not bodies and not errors:
        return [{"_error": "no LinkedIn alert source configured "
                           "(set LINKEDIN_IMAP_* or LINKEDIN_ALERT_DIR) - see "
                           "jobradar/sources/linkedin_alerts.py for setup"}]

    out: list = []
    seen: set[str] = set()
    for html, received in bodies:
        for j in parse_alert(html, received):
            if j.source_id in seen:
                continue
            seen.add(j.source_id)
            if too_old(j.date_published, cfg["sources"]["max_age_days"]):
                continue
            out.append(j)
    if errors:
        out.append({"_error": "; ".join(errors[:2])})
    return out
