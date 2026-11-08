"""Explainable weighted scoring.

Pipeline per job:  geo -> category/seniority -> industry -> salary -> score.
A hard exclusion can never be overridden by a high score: excluded jobs keep
their computed dimension scores for transparency but are reported as ineligible
and are never notified or shortlisted.
"""
from __future__ import annotations

from ..enrich import category, geo, industry, salary


def evaluate(job, cfg) -> None:
    # ---- enrichment (order matters: geo & industry feed each other) ------
    geo.classify(job, cfg)
    category.classify(job, cfg)
    industry.classify(job, cfg)
    salary.estimate(job, cfg)

    # ---- dimensions ------------------------------------------------------
    g_score, g_rank, g_pos, g_neg = geo.tier_score(job, cfg)
    s_score, s_pos, s_neg = category.skills_score(job, cfg)
    c_score, c_pos, c_neg = salary.score(job, cfg)
    n_score, n_pos, n_neg = category.seniority_score(job, cfg)
    i_score, i_pos, i_neg, i_penalty = industry.score(job, cfg)
    r_score, r_pos, r_neg = category.career_score(job, cfg)

    job.geo_tier_rank = g_rank
    job.dimension_scores = {
        "geography": g_score, "skills": s_score, "compensation": c_score,
        "seniority": n_score, "industry": i_score, "career": r_score,
    }

    w = cfg["weights"]
    weighted = (
        g_score * w["geography"] + s_score * w["skills"] + c_score * w["compensation"]
        + n_score * w["seniority"] + i_score * w["industry"] + r_score * w["career"]
    ) / 100.0

    # ---- penalties -------------------------------------------------------
    penalties: list[tuple[str, float]] = []
    if i_penalty:
        penalties.append(("Forex/CFD industry", i_penalty))

    comp = cfg["compensation"]
    if job.meets_80k == "No" and job.salary_confidence != "High":
        penalties.append((f"Estimated below the EUR{comp['floor_gr_at_eur']:,} floor",
                          comp["estimated_below_floor_penalty"]))
    elif job.meets_80k == "Borderline":
        penalties.append((f"Estimated range straddles the EUR{comp['floor_gr_at_eur']:,} floor",
                          comp["estimated_below_floor_penalty"] / 2))
    if not job.assessment_complete:
        penalties.append(("Incomplete assessment (job description unavailable)", 8))
    if "scope_unstated" in job.tags:
        penalties.append(("Remote scope not stated - eligibility unverified", 8))
    if job.salary_confidence == "Low":
        penalties.append(("Low-confidence salary estimate", 4))
    if job.work_arrangement == "unknown":
        penalties.append(("Work arrangement unconfirmed", 3))

    total_penalty = sum(p for _, p in penalties)
    job.penalties = penalties
    job.score = round(max(0.0, min(100.0, weighted - total_penalty)), 1)

    # ---- hard-exclusion gate (after scoring, so we can show the delta) ---
    if not job.eligible:
        job.score = 0.0

    # ---- published salary below floor = hard exclusion -------------------
    if (job.eligible and job.salary_confidence == "High"
            and not job.salary_is_floor
            and cfg["exclusions"]["below_salary_floor"]["enabled"]
            and job.geo_tier in ("onsite_athens", "remote_greece",
                                 "onsite_vienna", "remote_austria")
            and job.salary_published_max
            and job.salary_published_max < comp["floor_gr_at_eur"]):
        job.eligible = False
        job.score = 0.0
        job.exclusion_reasons.append(
            f"{cfg['exclusions']['below_salary_floor']['reason']} "
            f"(published max EUR{job.salary_published_max:,.0f} "
            f"< EUR{comp['floor_gr_at_eur']:,})")

    # ---- explanation -----------------------------------------------------
    job.positives = _dedup(g_pos + s_pos + c_pos + n_pos + i_pos + r_pos)
    job.negatives = _dedup(job.negatives + g_neg + s_neg + c_neg + n_neg + i_neg + r_neg
                           + [f"Penalty -{v:.0f}: {k}" for k, v in penalties])
    job.missing_info = _dedup(job.missing_info)
    job.job_fit = _fit_sentence(job, cfg)


def _dedup(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _fit_sentence(job, cfg) -> str:
    if not job.eligible:
        return "EXCLUDED: " + "; ".join(job.exclusion_reasons)
    tier_txt = {"tier1": "core expertise (BI/DWH/Analytics Eng/Platform)",
                "tier2": "data-engineering leadership",
                "tier3": "analytics/reporting leadership"}.get(
                    job.category_tier, "outside the target categories")
    d = job.dimension_scores
    strongest = max(d, key=d.get)
    weakest = min(d, key=d.get)
    return (f"{job.seniority.replace('_', ' ').title() or 'Unknown'}-level "
            f"{tier_txt}; {job.remote_eligibility}. "
            f"Strongest dimension: {strongest} ({d[strongest]:.0f}/100); "
            f"weakest: {weakest} ({d[weakest]:.0f}/100).")


def score_breakdown(job, cfg) -> str:
    """Human-readable audit trail of exactly how the score was produced."""
    w = cfg["weights"]
    lines = [f"{'Dimension':<14}{'Score':>7}{'Weight':>8}{'Contribution':>14}"]
    total = 0.0
    for k, v in job.dimension_scores.items():
        contrib = v * w[k] / 100.0
        total += contrib
        lines.append(f"{k:<14}{v:>7.1f}{w[k]:>8}{contrib:>14.2f}")
    lines.append(f"{'SUBTOTAL':<14}{'':>7}{'':>8}{total:>14.2f}")
    for name, val in job.penalties:
        lines.append(f"{'penalty':<14}{'':>7}{'':>8}{-val:>14.2f}  {name}")
    lines.append(f"{'FINAL':<14}{'':>7}{'':>8}{job.score:>14.2f}")
    return "\n".join(lines)
