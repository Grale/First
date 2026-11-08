"""Telegram notifications with per-job deduplication.

Credentials come from the environment only, never from code or config:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import os
import time

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_message(job, kind: str = "new") -> str:
    header = {"new": "\U0001F3AF <b>New match</b>",
              "changed": "\U0001F504 <b>Updated posting</b>"}[kind]
    sal = "not published"
    if job.salary_est_min:
        sal = (f"EUR{job.salary_est_min:,.0f}-{job.salary_est_max:,.0f} "
               f"({job.salary_confidence.lower()} confidence)")
    reasons = [p for p in job.positives if not p.startswith("Skill-group")][:3]
    concerns = [n for n in job.negatives if not n.startswith("Penalty")][:2]

    lines = [
        header,
        f"<b>{_esc(job.title)}</b>",
        f"\U0001F3E2 {_esc(job.company)}  ·  {_esc(job.industry.replace('_', ' '))}",
        f"\U0001F4CD {_esc(job.raw_location or job.country)}  ·  {_esc(job.work_arrangement)}",
        f"\U0001F30D {_esc(job.remote_eligibility)}",
        f"⭐ <b>Score {job.score:.0f}/100</b>",
        f"\U0001F4B6 {_esc(sal)}",
    ]
    if job.net_monthly_gr:
        lines.append(f"   ↳ indicative net: GR EUR{job.net_monthly_gr:,.0f}/mo · "
                     f"CY EUR{job.net_monthly_cy:,.0f}/mo")
    if reasons:
        lines.append("\n<b>Why it is relevant</b>")
        lines += [f"• {_esc(r)}" for r in reasons]
    if concerns:
        lines.append("\n<b>Concerns</b>")
        lines += [f"• {_esc(c)}" for c in concerns]
    lines.append(f"\n\U0001F517 <a href=\"{_esc(job.url)}\">Full job description</a>")
    return "\n".join(lines)


def send(text: str, timeout: int = 20) -> tuple[bool, str]:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"
    try:
        r = requests.post(API.format(token=token),
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": False},
                          timeout=timeout)
        if r.status_code == 200:
            return True, "sent"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:                          # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def notify_new(jobs: list, store, cfg, dry_run: bool = False) -> dict:
    """Send one message per genuinely new eligible job above the threshold.

    Deduplication is handled by the notifications ledger in the store, keyed on
    the job fingerprint (canonical URL, else company+title+country), so the same
    posting found on several boards notifies at most once.
    """
    threshold = cfg["output"]["notify_min_score"]
    sent, skipped, failed, previews = 0, 0, 0, []
    for job in jobs:
        if not job.eligible or job.score < threshold:
            continue
        fp = job.fingerprint()
        if store.already_notified(fp, "new"):
            skipped += 1
            continue
        msg = format_message(job, "new")
        if dry_run:
            previews.append(msg)
            store.mark_notified(fp, "new", "dry-run")
            sent += 1
            continue
        ok, detail = send(msg)
        if ok:
            store.mark_notified(fp, "new", detail)
            sent += 1
            time.sleep(1.2)                 # stay inside Telegram rate limits
        else:
            failed += 1
            previews.append(f"[FAILED {detail}]\n{msg}")
    return {"sent": sent, "skipped_duplicate": skipped, "failed": failed,
            "previews": previews}
