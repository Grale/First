"""HTML -> text, date parsing, salary string parsing, URL canonicalisation."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

_WS = re.compile(r"[ \t\xa0]+")
_NL = re.compile(r"\n{3,}")

TRACKING_PREFIXES = ("utm_", "gh_", "ref", "source", "src", "trk", "lever-", "mc_")


def html_to_text(html: str) -> str:
    if not html:
        return ""
    if "<" not in html:
        return clean_text(html)
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "noscript"]):
        bad.decompose()
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    for blk in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "tr"]):
        blk.append("\n")
    return clean_text(soup.get_text(" "))


def clean_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _NL.sub("\n\n", text).strip()


def canonical_url(url: str) -> str:
    """Strip tracking params and fragments so the same posting dedups cleanly."""
    if not url:
        return ""
    try:
        s = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    host = s.netloc.lower().removeprefix("www.")
    query = "&".join(
        kv for kv in s.query.split("&")
        if kv and not kv.split("=")[0].lower().startswith(TRACKING_PREFIXES)
    )
    path = s.path.rstrip("/") or "/"
    return urlunsplit((s.scheme or "https", host, path, query, ""))


def parse_date(value) -> str:
    """Best-effort -> ISO yyyy-mm-dd."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
        except (OSError, ValueError, OverflowError):
            return ""
    s = str(value).strip()
    fmts = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%d %b %Y")
    for f in fmts:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


_CUR = {"eur": "EUR", "€": "EUR", "usd": "USD", "$": "USD", "gbp": "GBP", "£": "GBP",
        "chf": "CHF", "pln": "PLN", "sek": "SEK"}
_FX_TO_EUR = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17, "CHF": 1.05, "PLN": 0.23, "SEK": 0.088}

_AMOUNT = r"\d{1,3}(?:[.,\s]\d{3})+|\d{2,3}(?:[.,]\d)?\s?[kK]\b|\d{4,6}"
_SALARY_RE = re.compile(
    r"(?P<cur>€|\$|£|EUR|USD|GBP|CHF)?\s?"
    rf"(?P<a>{_AMOUNT})"
    r"(?:\s*(?:EUR|USD|GBP|CHF|€|\$|£))?"
    r"\s*(?:-|–|—|to|bis|until|and)\s*"
    r"(?P<cur2>€|\$|£|EUR|USD|GBP|CHF)?\s?"
    rf"(?P<b>{_AMOUNT})"
    r"\s*(?P<cur3>€|\$|£|EUR|USD|GBP|CHF)?",
    re.IGNORECASE,
)


_SHORT_K_RE = re.compile(
    r"(?P<a>\d{2,3})\s*(?:-|–|—|to|and|bis)\s*(?P<b>\d{2,3})\s?[kK]\b", re.IGNORECASE)
_THOUSANDS = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_DECIMAL = re.compile(r"^\d+[.,]\d{1,2}$")


def _num(tok: str) -> float | None:
    """Parse '90,000' / '75.000' / '95k' / '1.5k' into a float."""
    t = tok.strip().lower().replace(" ", "")
    mult = 1.0
    if t.endswith("k"):
        t, mult = t[:-1].strip(), 1000.0
    if _THOUSANDS.match(t):              # 75.000 or 90,000 -> thousands groups
        t = t.replace(".", "").replace(",", "")
    elif _DECIMAL.match(t):              # 1.5k -> decimal
        t = t.replace(",", ".")
    else:
        t = t.replace(",", "").replace(" ", "")
    try:
        v = float(t) * mult
    except ValueError:
        return None
    return v if 1000 <= v <= 1_000_000 else None


def parse_salary(text: str) -> tuple[float | None, float | None, str, str]:
    """Return (min_eur, max_eur, currency, raw_match). Annualises monthly figures."""
    if not text:
        return None, None, "", ""
    window = text[:6000]
    m = _SALARY_RE.search(window)
    if not m:
        m2 = _SHORT_K_RE.search(window)
        if not m2:
            return None, None, "", ""
        lo, hi = float(m2.group("a")) * 1000, float(m2.group("b")) * 1000
        if hi < lo or lo < 10000:
            return None, None, "", ""
        ctx2 = window[max(0, m2.start() - 90): m2.end() + 90].lower()
        cur2 = next((v for k, v in _CUR.items() if k in ctx2), "EUR")
        return (round(lo * _FX_TO_EUR.get(cur2, 1.0)),
                round(hi * _FX_TO_EUR.get(cur2, 1.0)), cur2, m2.group(0).strip())
    lo, hi = _num(m.group("a")), _num(m.group("b"))
    if lo is None or hi is None or hi < lo:
        return None, None, "", ""
    cur_tok = (m.group("cur") or m.group("cur2") or m.group("cur3") or "").lower()
    cur = _CUR.get(cur_tok, "")
    ctx = window[max(0, m.start() - 90): m.end() + 90].lower()
    if not cur:
        for k, v in _CUR.items():
            if k in ctx:
                cur = v
                break
    cur = cur or "EUR"
    # monthly -> annual
    if re.search(r"\b(per hour|/h\b|hourly|per day|/day|daily)\b", ctx):
        return None, None, "", ""
    if re.search(r"(per month|/month|monthly|pro monat|μηνια|a month|p\.m\.)", ctx):
        # Austrian/Greek 14-salary schemes pay 14 monthly instalments a year.
        months = 14 if re.search(r"\b14\s*(x|mal|gehälter|salaries|payments)", ctx) else 12
        lo, hi = lo * months, hi * months
    rate = _FX_TO_EUR.get(cur, 1.0)
    return round(lo * rate), round(hi * rate), cur, m.group(0).strip()
