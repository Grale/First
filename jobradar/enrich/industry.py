"""Industry inference, with careful Forex/CFD-brokerage detection.

The brief is explicit: ordinary banking, insurance and fintech must NOT be
confused with Forex/CFD brokers, so forex detection requires brokerage-specific
evidence (CFDs, MetaTrader, spreads/leverage, CySEC-regulated brokerage), not
merely the word 'trading' or 'broker'.
"""
from __future__ import annotations

import re

FOREX_STRONG = re.compile(
    r"\b(cfd[s]?\b|contracts? for difference|forex broker|fx broker|foreign exchange broker|"
    r"metatrader|mt4|mt5|ctrader|spread betting|margin trading|retail (trading|broker)|"
    r"online trading platform|prop(rietary)? trading firm|liquidity provider|"
    r"tier[- ]1 liquidity|trading (accounts?|conditions)|leveraged products|"
    r"introducing broker|white label broker)\b", re.I)
FOREX_SUPPORT = re.compile(
    r"\b(cysec|forex|fx\b|trading platform|broker(age)?|spreads?|pips?|leverage|"
    r"client funds|execution venue|stp|ecn)\b", re.I)
KNOWN_FOREX = re.compile(
    r"\b(exness|xm\.com|xtb|ic ?markets|fxpro|fxtm|hotforex|hfm\b|plus500|etoro|avatrade|"
    r"pepperstone|admirals|tickmill|ironfx|easymarkets|libertex|naga|trading ?212|"
    r"capital\.com|markets\.com|oanda|swissquote|cmc markets|ig group|saxo bank|"
    r"ingot|scope markets|vantage|eightcap|blueberry markets|fxview|windsor broker)\b", re.I)

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("technology_saas", re.compile(
        r"\b(saas|software[- ]as[- ]a[- ]service|developer (platform|tools)|cloud platform|"
        r"api platform|open source|b2b software|enterprise software|devops|observability|"
        r"cyber ?security|infrastructure software|product[- ]led)\b", re.I)),
    ("telecom", re.compile(r"\b(telecom|telecommunication|mobile network|5g|broadband|mvno|isp)\b", re.I)),
    ("ecommerce_retail", re.compile(
        r"\b(e-?commerce|marketplace|online (shop|store|retail)|retailer|retail chain|"
        r"consumer goods|fmcg|grocery|fashion|d2c|direct[- ]to[- ]consumer|"
        r"food delivery|q-?commerce)\b", re.I)),
    ("energy", re.compile(r"\b(energy|renewable|utilit(y|ies)|oil (and|&) gas|petroleum|solar|wind farm|"
                          r"electricity|natural gas|power grid|hydrogen)\b", re.I)),
    ("healthcare", re.compile(r"\b(health ?care|healthtech|medtech|pharma|biotech|clinical|patient|"
                              r"hospital|life sciences|medical device|digital health)\b", re.I)),
    ("manufacturing", re.compile(r"\b(manufactur|industrial|factory|production plant|automotive|"
                                 r"machinery|assembly line|supply chain manufacturing)\b", re.I)),
    ("logistics", re.compile(r"\b(logistics|freight|shipping|maritime|supply chain|fleet|"
                             r"last[- ]mile|warehous(e|ing) operations|transportation|courier)\b", re.I)),
    ("consulting", re.compile(r"\b(consultanc|consulting firm|advisory|professional services|"
                              r"system integrator|big four|client engagements)\b", re.I)),
    ("gaming_igaming", re.compile(r"\b(igaming|online casino|sportsbook|betting|gambling|"
                                  r"game studio|video game|mobile gaming|slots)\b", re.I)),
    ("fintech_banking", re.compile(
        r"\b(fintech|neobank|digital bank|banking|payments?|payment (service|processing)|"
        r"insurance|insurtech|lending|credit|wealth ?(tech|management)|regtech|"
        r"card issuing|acquiring|psp|embedded finance|accounting software|treasury)\b", re.I)),
    ("public_nonprofit", re.compile(r"\b(non[- ]?profit|ngo|charit|public sector|government|"
                                    r"ministry|municipal|united nations|foundation)\b", re.I)),
]


def classify(job, cfg) -> None:
    # A curated value from the ATS registry always wins.
    if job.industry and job.industry != "other":
        _forex_rules(job, cfg)
        return

    blob = f"{job.company}\n{job.title}\n{job.description[:6000]}"
    if KNOWN_FOREX.search(job.company) or (
            len(FOREX_STRONG.findall(blob)) >= 2) or (
            FOREX_STRONG.search(blob) and len(FOREX_SUPPORT.findall(blob)) >= 3):
        job.industry = "forex_cfd"
        _forex_rules(job, cfg)
        return

    best, best_n = "other", 0
    for name, rx in PATTERNS:
        n = len(rx.findall(blob))
        if n > best_n:
            best, best_n = name, n
    job.industry = best if best_n >= 2 else "other"
    if job.industry == "other":
        job.missing_info.append("Industry could not be determined from the posting")
    _forex_rules(job, cfg)


def _forex_rules(job, cfg) -> None:
    """Forex-specific hard exclusion and penalties."""
    if job.industry != "forex_cfd":
        return
    ex = cfg["exclusions"]["forex_cyprus_onsite"]
    if ex["enabled"] and job.country == "CY" and job.work_arrangement in ("onsite", "hybrid"):
        job.eligible = False
        job.exclusion_reasons.append(ex["reason"])
        return
    job.negatives.append(
        "Forex/CFD brokerage - the sector the candidate explicitly wants to leave")


def score(job, cfg) -> tuple[float, list[str], list[str], float]:
    """Return (0-100 industry score, positives, negatives, extra_penalty)."""
    scores = cfg["industry"]["scores"]
    s = float(scores.get(job.industry, scores["other"]))
    pos, neg, penalty = [], [], 0.0
    label = job.industry.replace("_", " ")

    if job.industry == "forex_cfd":
        penalty = cfg["industry"]["forex_remote_penalty"]
        neg.append(f"Industry is Forex/CFD - heavy penalty applied (-{penalty:.0f} overall)")
    elif job.industry == "other":
        neg.append("Industry unknown - scored at the neutral default")
    else:
        if job.industry != cfg["candidate"]["current_industry"]:
            s += cfg["industry"]["current_industry_change_bonus"]
            pos.append(f"Industry change into {label} (away from Forex/CFD)")
        else:
            pos.append(f"Industry: {label}")
    return max(0.0, min(100.0, s)), pos, neg, penalty
