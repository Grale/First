"""Salary estimation and indicative net-income modelling.

Distinguishes PUBLISHED salary from an ESTIMATE, always reports a range and a
confidence level, and never claims a precision the evidence does not support.
Net figures are indicative only - not tax advice.
"""
from __future__ import annotations


def _bench_key(job) -> str:
    return {"director": "director", "head": "head", "manager": "manager",
            "lead": "lead", "principal": "principal"}.get(job.seniority, "manager")


def _bench_country(job) -> str:
    if job.geo_tier in ("onsite_athens", "remote_greece"):
        return "GR"
    if job.geo_tier in ("onsite_vienna", "remote_austria"):
        return "AT"
    if job.geo_tier == "remote_cyprus":
        return "CY"
    return "EU_REMOTE"


def estimate(job, cfg) -> None:
    comp = cfg["compensation"]
    # ---------------- published ------------------------------------------
    if job.salary_published_min and job.salary_published_max:
        job.salary_est_min = job.salary_published_min
        job.salary_est_max = job.salary_published_max
        job.salary_confidence = "High"
        job.salary_basis = f"Published in the posting ({job.published_salary_raw or 'explicit range'})"
    else:
        key, country = _bench_key(job), _bench_country(job)
        p25, med, p75 = comp["benchmarks"][country][key]
        cm = comp["company_multipliers"].get(job.company_size_bucket, 1.0)
        im = comp["industry_multipliers"].get(job.industry, 1.0)
        mult = cm * im
        job.salary_est_min = round(p25 * mult / 500) * 500
        job.salary_est_max = round(p75 * mult / 500) * 500
        known = sum([bool(job.company_size_bucket), job.industry != "other",
                     country != "EU_REMOTE", job.seniority in
                     ("director", "head", "manager", "lead", "principal")])
        job.salary_confidence = "Medium" if known >= 3 else "Low"
        job.salary_basis = (
            f"Estimated: {country} {key} benchmark EUR{p25:,}-{p75:,} "
            f"x company {cm:.2f} x industry {im:.2f}"
            + ("" if job.company_size_bucket else "; company size unknown"))
        job.missing_info.append("Salary not published - figure is a benchmark estimate")

    mid = (job.salary_est_min + job.salary_est_max) / 2
    job.total_comp_est = _total_comp(job, mid)

    # ---------------- 80k test -------------------------------------------
    country = _bench_country(job)
    if country in ("GR", "AT"):
        floor = comp["floor_gr_at_eur"]
        if job.salary_est_max < floor:
            job.meets_80k = "No"
        elif job.salary_est_min >= floor:
            job.meets_80k = "Yes"
        else:
            job.meets_80k = "Borderline"
    else:
        job.meets_80k = "Yes" if mid >= comp["floor_gr_at_eur"] else "Borderline"

    # ---------------- net ------------------------------------------------
    job.net_monthly_gr = round(net_monthly(mid, "GR", cfg), 0)
    job.net_monthly_cy = round(net_monthly(mid, "CY", cfg), 0)


def _total_comp(job, mid: float) -> str:
    body = (job.description or "").lower()
    extras = []
    if any(w in body for w in ("equity", "stock option", "rsu", "share option", "esop")):
        extras.append("equity")
    if any(w in body for w in ("bonus", "performance pay", "variable pay", "incentive")):
        extras.append("bonus")
    if not extras:
        return f"~EUR{mid:,.0f} base (no bonus/equity mentioned)"
    uplift = 1.20 if "equity" in extras and "bonus" in extras else 1.10
    return f"~EUR{mid * uplift:,.0f} incl. {' + '.join(extras)}"


def _progressive(income: float, brackets: list) -> float:
    tax, left = 0.0, income
    for width, rate in brackets:
        if left <= 0:
            break
        take = left if width is None else min(left, float(width))
        tax += take * float(rate)
        left -= take
    return tax


def net_monthly(gross_annual: float, country: str, cfg,
                apply_exemption: bool = True) -> float:
    """Indicative monthly net. Applies the 50% exemption where configured."""
    t = cfg["tax"].get(country)
    if not t or not gross_annual:
        return 0.0

    if country == "GR":
        cap = t["social_monthly_ceiling_eur"] * 12
        social = min(gross_annual, cap) * t["social_employee_rate"]
        taxable = gross_annual - social
        if apply_exemption and t["exemption_50pct"]["available"]:
            taxable *= 0.5
        tax = _progressive(taxable, t["brackets"])
        return (gross_annual - social - tax) / 12

    if country == "CY":
        social = min(gross_annual, t["social_annual_ceiling_eur"]) * t["social_employee_rate"]
        ghs = min(gross_annual, t["ghs_annual_ceiling_eur"]) * t["ghs_rate"]
        taxable = gross_annual
        # The 50% relief applies to emoluments above the EUR55k threshold.
        if apply_exemption and t["exemption_50pct"]["available"] and gross_annual > 55000:
            taxable = gross_annual * 0.5
        taxable = max(0.0, taxable - social - ghs)
        tax = _progressive(taxable, t["brackets"])
        return (gross_annual - social - ghs - tax) / 12

    if country == "AT":
        cap = t["social_monthly_ceiling_eur"] * 12
        social = min(gross_annual, cap) * t["social_employee_rate"]
        # 13th/14th salaries are taxed at 6%; approximate by splitting 2/14.
        regular = gross_annual * 12 / 14
        special = gross_annual * 2 / 14
        soc_reg = social * 12 / 14
        tax = _progressive(max(0.0, regular - soc_reg), t["brackets"]) + special * 0.06
        return (gross_annual - social - tax) / 12
    return 0.0


def score(job, cfg) -> tuple[float, list[str], list[str]]:
    """0-100 compensation attractiveness vs the candidate's current package."""
    comp = cfg["compensation"]
    pos, neg = [], []
    cur_net = comp["current_net_monthly_eur"]
    country = _bench_country(job)
    mid = ((job.salary_est_min or 0) + (job.salary_est_max or 0)) / 2
    if not mid:
        return 35.0, [], ["No salary information and no usable benchmark"]

    # Compare on the net the candidate would realistically take home.
    net = job.net_monthly_gr if country == "GR" else (
        job.net_monthly_cy if country == "CY" else
        net_monthly(mid, "AT", cfg) if country == "AT" else
        max(job.net_monthly_gr or 0, job.net_monthly_cy or 0))
    net = net or 0.0
    ratio = net / cur_net if cur_net else 1.0
    # 0.75x current -> 25 ; 1.0x -> 60 ; 1.3x -> 90 ; 1.5x+ -> 100
    s = max(0.0, min(100.0, (ratio - 0.70) / 0.80 * 100.0))

    if job.salary_confidence == "High":
        pos.append(f"Salary published: EUR{job.salary_est_min:,.0f}-{job.salary_est_max:,.0f}")
    else:
        s *= 0.92                       # estimate uncertainty discount
        neg.append(f"Salary estimated ({job.salary_confidence} confidence), not published")

    if mid >= comp["stretch_target_eur"]:
        pos.append(f"Estimated package above EUR{comp['stretch_target_eur']:,} ")
    if ratio >= 1.15:
        pos.append(f"Indicative net ~EUR{net:,.0f}/mo vs current EUR{cur_net:,} (+{(ratio-1)*100:.0f}%)")
    elif ratio < 0.95:
        neg.append(f"Indicative net ~EUR{net:,.0f}/mo vs current EUR{cur_net:,} ({(ratio-1)*100:.0f}%)")

    if job.meets_80k == "No":
        neg.append(f"Below the EUR{comp['floor_gr_at_eur']:,} floor for {country}")
    elif job.meets_80k == "Borderline":
        neg.append(f"Borderline against the EUR{comp['floor_gr_at_eur']:,} floor")
    return round(s, 1), pos, neg
